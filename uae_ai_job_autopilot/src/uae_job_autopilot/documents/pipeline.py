from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Iterable

from uae_job_autopilot.config import (
    DEFAULT_DATA_DIR,
    Settings,
    get_settings,
)
from uae_job_autopilot.db.repository import ApplicationRepository
from uae_job_autopilot.documents.generator import DocumentPipeline, GeneratedDocuments, application_key
from uae_job_autopilot.documents.master import build_master_resume
from uae_job_autopilot.domain.enums import MatchDecision
from uae_job_autopilot.domain.models import JobMatchResult, JobPosting
from uae_job_autopilot.reporting.gmail import (
    build_daily_report_email,
    build_email_client,
    send_daily_report_with_recovery,
)
from uae_job_autopilot.tracking.sheets import build_sheets_client, sync_phase3_workbook
from uae_job_autopilot.utils.timeutil import utcnow

logger = logging.getLogger(__name__)


class Phase3Report:
    def __init__(self) -> None:
        self.run_id = utcnow().strftime("%Y%m%dT%H%M%SZ") + "-p3-" + uuid.uuid4().hex[:8]
        self.started_at = utcnow()
        self.finished_at = None
        self.documents: list[GeneratedDocuments] = []
        self.stats: dict[str, Any] = {
            "jobs_considered": 0,
            "documents_generated": 0,
            "ats_pass": 0,
            "ats_fail": 0,
            "integrity_fail": 0,
            "db_upserts": 0,
            "sheets_ok": True,
            "email_status": None,
        }
        self.notes: list[str] = []
        self.failures: list[str] = []
        self.sheets_result: dict[str, Any] = {}
        self.email_result: dict[str, Any] = {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "stats": self.stats,
            "notes": self.notes,
            "failures": self.failures,
            "sheets_result": self.sheets_result,
            "email_result": self.email_result,
            "documents": [d.model_dump() for d in self.documents],
        }


class Phase3Pipeline:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        repo: ApplicationRepository | None = None,
        docs: DocumentPipeline | None = None,
        sheets=None,
        email=None,
        data_dir: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        # Normalize sqlite relative path under package data
        db_url = self.settings.database_url
        if db_url.startswith("sqlite:///./"):
            data_dir = data_dir or DEFAULT_DATA_DIR
            db_path = data_dir / "db" / "uae_jobs.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{db_path}"
        self.repo = repo or ApplicationRepository.from_url(db_url)
        self.docs = docs or DocumentPipeline(settings=self.settings, data_dir=data_dir or DEFAULT_DATA_DIR)
        self.sheets = sheets or build_sheets_client(self.settings)
        self.email = email or build_email_client(self.settings)
        self.data_dir = data_dir or DEFAULT_DATA_DIR

    def ensure_master(self) -> None:
        build_master_resume(persist=True)

    def prepare_documents_for_matches(
        self,
        matches: Iterable[JobMatchResult],
        *,
        send_email: bool = True,
        sync_sheets: bool = True,
        discovery_stats: dict[str, Any] | None = None,
        sources_queried: list[str] | None = None,
        sources_unavailable: list[dict[str, Any]] | None = None,
        discovery_unavailable: bool = False,
    ) -> Phase3Report:
        report = Phase3Report()
        self.ensure_master()
        match_list = list(matches)
        # Only prepare docs for PASS decisions; still persist rejects
        for m in match_list:
            report.stats["jobs_considered"] += 1
            key = application_key(m.job)
            if m.decision != MatchDecision.PASS:
                self.repo.upsert_application(
                    {
                        "application_key": key,
                        "employer": m.job.employer,
                        "title": m.job.title,
                        "location": m.job.location_raw,
                        "application_url": m.job.application_url,
                        "source": m.job.source,
                        "source_job_id": m.job.source_job_id,
                        "status": "rejected" if m.decision == MatchDecision.REJECT else "blocked",
                        "decision": str(m.decision),
                        "resume_score": m.resume_fit.combined_score if m.resume_fit else None,
                        "visa_score": m.visa.combined_score if m.visa else None,
                        "sponsorship_label": str(m.visa.sponsorship_label) if m.visa else "unknown",
                        "sponsorship_confirmed": bool(m.visa.sponsorship_confirmed) if m.visa else False,
                        "rejection_reason": "; ".join(h.code for h in m.hard_exclusions)
                        or str(m.decision),
                    }
                )
                report.stats["db_upserts"] += 1
                continue

            generated = self.docs.generate_for_job(m.job)
            report.documents.append(generated)
            report.stats["documents_generated"] += 1
            if generated.ats.passed:
                report.stats["ats_pass"] += 1
            else:
                report.stats["ats_fail"] += 1
            if not generated.integrity_ok:
                report.stats["integrity_fail"] += 1
                report.failures.append(
                    f"integrity:{key}:{','.join(generated.integrity_issues)}"
                )

            self.repo.upsert_application(
                {
                    "application_key": key,
                    "employer": m.job.employer,
                    "title": m.job.title,
                    "location": m.job.location_raw,
                    "application_url": m.job.application_url,
                    "source": m.job.source,
                    "source_job_id": m.job.source_job_id,
                    "status": "prepared" if generated.ats.passed else "ats_failed",
                    "decision": str(m.decision),
                    "resume_score": m.resume_fit.combined_score if m.resume_fit else None,
                    "visa_score": m.visa.combined_score if m.visa else None,
                    "ats_score": generated.ats.combined_score,
                    "ats_passed": generated.ats.passed,
                    "sponsorship_label": str(m.visa.sponsorship_label) if m.visa else "unknown",
                    "sponsorship_confirmed": bool(m.visa.sponsorship_confirmed) if m.visa else False,
                    "resume_version": generated.resume_version,
                    "cover_version": generated.cover_version,
                    "resume_pdf_path": generated.resume_pdf,
                    "cover_pdf_path": generated.cover_pdf,
                    "rejection_reason": None
                    if generated.ats.passed
                    else f"ATS {generated.ats.combined_score} < {generated.ats.threshold}",
                }
            )
            report.stats["db_upserts"] += 1

        apps = self.repo.list_applications()
        app_rows = [
            {
                "application_key": a.application_key,
                "employer": a.employer,
                "title": a.title,
                "location": a.location,
                "url": a.application_url,
                "status": a.status,
                "decision": a.decision,
                "resume_score": a.resume_score,
                "visa_score": a.visa_score,
                "ats_score": a.ats_score,
                "ats_passed": a.ats_passed,
                "resume_version": a.resume_version,
                "cover_version": a.cover_version,
                "sponsorship_confirmed": a.sponsorship_confirmed,
            }
            for a in apps
        ]
        today = [
            r
            for r in app_rows
            if r["status"] in {"prepared", "ats_failed"}
        ]
        rejected = [r for r in app_rows if r["status"] in {"rejected", "blocked"}]

        report.finished_at = utcnow()
        self.repo.record_run(
            run_id=report.run_id,
            phase="phase3",
            started_at=report.started_at,
            finished_at=report.finished_at,
            stats=report.stats,
            notes=report.notes,
            cost_usd=0.0,
        )

        if sync_sheets:
            dashboard = {
                "run_id": report.run_id,
                "documents_generated": report.stats["documents_generated"],
                "ats_pass": report.stats["ats_pass"],
                "ats_fail": report.stats["ats_fail"],
                "applications_confirmed": 0,
                "updated_at": report.finished_at.isoformat(),
            }
            report.sheets_result = sync_phase3_workbook(
                self.sheets,
                dashboard=dashboard,
                applications=app_rows,
                today_jobs=today,
                rejected=rejected,
                run_history=[
                    {
                        "run_id": report.run_id,
                        "phase": "phase3",
                        "started_at": report.started_at.isoformat(),
                        "finished_at": report.finished_at.isoformat(),
                        "stats": json.dumps(report.stats),
                    }
                ],
                source_health=sources_unavailable or [],
                model_costs=[],
                recruiter_outreach=[],
            )
            report.stats["sheets_ok"] = bool(report.sheets_result.get("ok", True))
            if report.sheets_result.get("errors"):
                report.failures.extend(
                    f"sheets:{k}:{v}" for k, v in report.sheets_result["errors"].items()
                )

        zero_jobs = (discovery_stats or {}).get("jobs_selected_for_evaluation", 0) == 0 and not discovery_unavailable
        subject, body = build_daily_report_email(
            discovery_stats=discovery_stats,
            evaluation_stats=None,
            document_stats=report.stats,
            sources_queried=sources_queried or [],
            sources_unavailable=sources_unavailable or [],
            top_links=[a.application_url for a in apps if a.status == "prepared"][:10],
            model_cost_usd=0.0,
            failures=report.failures,
            discovery_unavailable=discovery_unavailable,
            zero_jobs=zero_jobs and report.stats["documents_generated"] == 0,
        )

        if send_email:
            report.email_result = send_daily_report_with_recovery(
                self.email,
                to=self.settings.report_to_email,
                subject=subject,
                body=body,
            )
            report.stats["email_status"] = report.email_result.get("status")
            if report.email_result.get("status") != "sent":
                report.failures.append(f"email:{report.email_result.get('error')}")

        out = self.data_dir / "runs" / f"{report.run_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
        return report

    def prepare_for_jobs(
        self,
        jobs: Iterable[JobPosting],
        *,
        send_email: bool = False,
        sync_sheets: bool = True,
    ) -> Phase3Report:
        """Document generation path without Phase 2 match objects (treat as prepared candidates)."""
        fake_matches = [
            JobMatchResult(job=j, decision=MatchDecision.PASS, next_action="advance") for j in jobs
        ]
        return self.prepare_documents_for_matches(
            fake_matches, send_email=send_email, sync_sheets=sync_sheets
        )
