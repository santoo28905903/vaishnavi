from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Iterable

from uae_job_autopilot.apply.answers import build_screening_answers
from uae_job_autopilot.apply.base import ApplyContext
from uae_job_autopilot.apply.channels import build_channel
from uae_job_autopilot.apply.channels.unsupported import UnsupportedChannel
from uae_job_autopilot.apply.channels_config import (
    ApplicationChannelsConfig,
    ChannelConfig,
    load_application_channels,
)
from uae_job_autopilot.apply.checklist import (
    BLOCKING_PRIOR_STATUSES,
    run_pre_submit_checklist,
)
from uae_job_autopilot.config import (
    DEFAULT_DATA_DIR,
    CandidateProfile,
    Settings,
    get_settings,
    load_candidate_profile,
)
from uae_job_autopilot.db.repository import ApplicationRepository
from uae_job_autopilot.documents.generator import application_key
from uae_job_autopilot.domain.enums import ApplicationStatus, ApplyOutcome
from uae_job_autopilot.domain.models import (
    ApplyAttemptResult,
    ApplyReport,
    ApplyStats,
    JobPosting,
)
from uae_job_autopilot.tracking.sheets import build_sheets_client, sync_phase3_workbook
from uae_job_autopilot.utils.timeutil import utcnow

logger = logging.getLogger(__name__)


class ApplyOrchestrator:
    """
    Phase 5 apply stage: allowlisted channels only, checklist gates, confirmation
    verification, duplicate protection, CAPTCHA/MFA → blocked + continue.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        channels: ApplicationChannelsConfig | None = None,
        repo: ApplicationRepository | None = None,
        profile: CandidateProfile | None = None,
        sheets=None,
        data_dir: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.channels = channels or load_application_channels()
        self.profile = profile or load_candidate_profile()
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        db_url = self.settings.database_url
        if db_url.startswith("sqlite:///./"):
            db_path = self.data_dir / "db" / "uae_jobs.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{db_path}"
        self.repo = repo or ApplicationRepository.from_url(db_url)
        self.sheets = sheets or build_sheets_client(self.settings)

    def run(
        self,
        candidates: Iterable[dict[str, Any] | JobPosting],
        *,
        dry_run: bool = False,
        sync_sheets: bool = True,
        force_scenario: str | None = None,
    ) -> ApplyReport:
        report = ApplyReport(
            run_id=utcnow().strftime("%Y%m%dT%H%M%SZ") + "-apply-" + uuid.uuid4().hex[:8],
            started_at=utcnow(),
            dry_run=dry_run,
            live_submission_enabled=bool(self.settings.enable_live_submission),
        )
        report.notes.append(
            f"live_submission={report.live_submission_enabled}; "
            f"channels={list(self.channels.channels)}"
        )

        for raw in candidates:
            report.stats.candidates += 1
            try:
                attempt = self._process_one(raw, dry_run=dry_run, force_scenario=force_scenario)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Apply candidate failed — continuing")
                report.failures.append(str(exc))
                report.stats.errors += 1
                continue
            report.attempts.append(attempt)
            self._tally(report.stats, attempt)
            self._persist_attempt(attempt, raw)
            # Continue to next job on block / unverified / unsupported

        # Optional recruiter outreach drafts (never auto-send)
        if self.channels.recruiter_outreach.get("drafts_enabled"):
            report.recruiter_drafts = self._recruiter_drafts(report.attempts)
            if self.channels.recruiter_outreach.get("auto_send"):
                report.notes.append(
                    "recruiter auto_send requested but ignored — not separately authorized"
                )

        report.finished_at = utcnow()
        self.repo.record_run(
            run_id=report.run_id,
            phase="phase5",
            started_at=report.started_at,
            finished_at=report.finished_at,
            stats=report.stats.model_dump(),
            notes=report.notes,
            cost_usd=0.0,
        )

        if sync_sheets:
            self._sync_sheets(report)

        out = self.data_dir / "runs" / f"{report.run_id}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )
        return report

    def _normalize_candidate(self, raw: dict[str, Any] | JobPosting) -> dict[str, Any]:
        if isinstance(raw, JobPosting):
            return {
                "job": raw,
                "application_key": application_key(raw),
                "resume_pdf": None,
                "cover_pdf": None,
                "ats_passed": True,
                "status": "prepared",
            }
        job_data = raw.get("job") or raw
        job = job_data if isinstance(job_data, JobPosting) else JobPosting.model_validate(job_data)
        return {
            "job": job,
            "application_key": raw.get("application_key") or application_key(job),
            "resume_pdf": raw.get("resume_pdf") or raw.get("resume_pdf_path"),
            "cover_pdf": raw.get("cover_pdf") or raw.get("cover_pdf_path"),
            "ats_passed": bool(raw.get("ats_passed", True)),
            "status": raw.get("status") or "prepared",
            "scenario": raw.get("scenario"),
        }

    def _process_one(
        self,
        raw: dict[str, Any] | JobPosting,
        *,
        dry_run: bool,
        force_scenario: str | None,
    ) -> ApplyAttemptResult:
        cand = self._normalize_candidate(raw)
        job: JobPosting = cand["job"]
        key = cand["application_key"]
        existing = self.repo.get_by_key(key)

        # Duplicate protection
        if existing and existing.status in BLOCKING_PRIOR_STATUSES:
            return ApplyAttemptResult(
                application_key=key,
                channel_id=existing.channel_id or "duplicate",
                outcome=ApplyOutcome.DUPLICATE,
                status=ApplicationStatus.DUPLICATE,
                dry_run=dry_run,
                block_reason=f"prior status={existing.status}",
                attempt_number=(existing.attempt_count or 0) + 1,
                submitted_at=utcnow(),
                notes=[f"duplicate protection: already {existing.status}"],
                evidence={"prior_status": existing.status},
            )

        answers = build_screening_answers(self.profile, job=job)
        channel_id = self.channels.resolve_channel_id(
            application_url=job.application_url, source=job.source
        )

        if channel_id is None:
            # Unsupported or no allowlisted match — never pretend we can submit
            cid = (
                "unsupported"
                if self.channels.is_unsupported_source(job.source)
                else "no_allowlisted_channel"
            )
            unsupported = UnsupportedChannel(channel_id=cid)
            ctx = ApplyContext(
                job=job,
                application_key=key,
                channel_id=cid,
                channel=ChannelConfig(
                    enabled=False,
                    authorized=False,
                    method="unsupported",
                    description="Not allowlisted for automated submission",
                ),
                answers=answers,
                resume_pdf=cand["resume_pdf"],
                cover_pdf=cand["cover_pdf"],
                dry_run=dry_run,
                live_submission_enabled=bool(self.settings.enable_live_submission),
            )
            return unsupported.submit(ctx)

        channel_cfg = self.channels.channels[channel_id]
        method_authorized = bool(channel_cfg.enabled and channel_cfg.authorized)
        checklist = run_pre_submit_checklist(
            answers=answers,
            channel_id=channel_id,
            channel=channel_cfg,
            existing=existing,
            resume_pdf=cand["resume_pdf"],
            cover_pdf=cand["cover_pdf"],
            ats_passed=bool(cand["ats_passed"]),
            live_submission_enabled=bool(self.settings.enable_live_submission),
            dry_run=dry_run,
            method_authorized=method_authorized,
        )
        if not checklist.passed:
            return ApplyAttemptResult(
                application_key=key,
                channel_id=channel_id,
                outcome=ApplyOutcome.CHECKLIST_FAILED,
                status=ApplicationStatus.BLOCKED,
                dry_run=dry_run,
                block_reason="pre-submit checklist failed: " + ",".join(checklist.blocking_codes),
                checklist=checklist,
                screening_answers=answers,
                submitted_at=utcnow(),
                notes=[f"checklist blocked: {checklist.blocking_codes}"],
                evidence={"checklist": checklist.model_dump()},
            )

        # Channel disabled / not authorized → honest skip (not applied)
        if not channel_cfg.enabled or not channel_cfg.authorized:
            if dry_run:
                return ApplyAttemptResult(
                    application_key=key,
                    channel_id=channel_id,
                    outcome=ApplyOutcome.DRY_RUN,
                    status=ApplicationStatus.DRY_RUN,
                    dry_run=True,
                    checklist=checklist,
                    screening_answers=answers,
                    submitted_at=utcnow(),
                    notes=[
                        f"dry_run: channel {channel_id} not enabled+authorized — "
                        "would not submit until explicitly authorized"
                    ],
                )
            return ApplyAttemptResult(
                application_key=key,
                channel_id=channel_id,
                outcome=ApplyOutcome.SKIPPED_UNSUPPORTED,
                status=ApplicationStatus.SKIPPED_UNSUPPORTED,
                dry_run=False,
                block_reason=f"channel {channel_id} not enabled+authorized",
                checklist=checklist,
                screening_answers=answers,
                submitted_at=utcnow(),
                notes=[f"channel {channel_id} disabled or unauthorized"],
            )

        # Live gate for channels that require it
        effective_dry = dry_run
        if (
            channel_cfg.requires_live_submission
            and not self.settings.enable_live_submission
            and not dry_run
        ):
            # Safety: force dry-run behavior rather than live submit
            effective_dry = True
            logger.warning(
                "ENABLE_LIVE_SUBMISSION=false — forcing dry-run for channel %s", channel_id
            )

        attempt_number = (existing.attempt_count if existing else 0) + 1
        max_attempts = self.channels.max_attempts()
        if attempt_number > max_attempts and existing and existing.status not in {
            "prepared",
            "ats_failed",
            "dry_run",
        }:
            return ApplyAttemptResult(
                application_key=key,
                channel_id=channel_id,
                outcome=ApplyOutcome.BLOCKED,
                status=ApplicationStatus.BLOCKED,
                dry_run=effective_dry,
                block_reason=f"max attempts {max_attempts} exceeded",
                attempt_number=attempt_number,
                checklist=checklist,
                screening_answers=answers,
                submitted_at=utcnow(),
                notes=["retry cap reached"],
            )

        adapter = build_channel(channel_id)
        ctx = ApplyContext(
            job=job,
            application_key=key,
            channel_id=channel_id,
            channel=channel_cfg,
            answers=answers,
            resume_pdf=cand["resume_pdf"],
            cover_pdf=cand["cover_pdf"],
            dry_run=effective_dry,
            live_submission_enabled=bool(self.settings.enable_live_submission),
            attempt_number=attempt_number,
            scenario=force_scenario or cand.get("scenario"),
        )
        result = adapter.submit(ctx)
        result.checklist = checklist
        if result.screening_answers is None:
            result.screening_answers = answers
        if effective_dry and not dry_run:
            result.notes = list(result.notes) + [
                "forced dry-run because ENABLE_LIVE_SUBMISSION=false"
            ]
        return result

    def _tally(self, stats: ApplyStats, attempt: ApplyAttemptResult) -> None:
        stats.attempted += 1
        mapping = {
            ApplyOutcome.APPLIED: "applied",
            ApplyOutcome.DRY_RUN: "dry_run",
            ApplyOutcome.BLOCKED: "blocked",
            ApplyOutcome.SUBMISSION_UNVERIFIED: "submission_unverified",
            ApplyOutcome.SKIPPED_UNSUPPORTED: "skipped_unsupported",
            ApplyOutcome.DUPLICATE: "duplicates",
            ApplyOutcome.CHECKLIST_FAILED: "checklist_failed",
            ApplyOutcome.ERROR: "errors",
        }
        attr = mapping.get(attempt.outcome)
        if attr:
            setattr(stats, attr, getattr(stats, attr) + 1)

    def _persist_attempt(
        self, attempt: ApplyAttemptResult, raw: dict[str, Any] | JobPosting
    ) -> None:
        cand = self._normalize_candidate(raw)
        job: JobPosting = cand["job"]
        existing = self.repo.get_by_key(attempt.application_key)
        retry_history: list[dict[str, Any]] = []
        if existing and existing.retry_history_json:
            try:
                retry_history = json.loads(existing.retry_history_json)
            except json.JSONDecodeError:
                retry_history = []
        retry_history.append(
            {
                "at": (attempt.submitted_at or utcnow()).isoformat(),
                "outcome": str(attempt.outcome),
                "status": str(attempt.status),
                "channel_id": attempt.channel_id,
                "block_reason": attempt.block_reason,
                "confirmation_verified": attempt.confirmation_verified,
                "confirmation_reference": attempt.confirmation_reference,
            }
        )
        self.repo.upsert_application(
            {
                "application_key": attempt.application_key,
                "employer": job.employer,
                "title": job.title,
                "location": job.location_raw,
                "application_url": job.application_url,
                "source": job.source,
                "source_job_id": job.source_job_id,
                "status": str(attempt.status),
                "decision": existing.decision if existing else "pass",
                "resume_score": existing.resume_score if existing else None,
                "visa_score": existing.visa_score if existing else None,
                "ats_score": existing.ats_score if existing else None,
                "ats_passed": existing.ats_passed if existing else bool(cand.get("ats_passed")),
                "sponsorship_label": existing.sponsorship_label if existing else "unknown",
                "sponsorship_confirmed": existing.sponsorship_confirmed if existing else False,
                "resume_version": existing.resume_version if existing else None,
                "cover_version": existing.cover_version if existing else None,
                "resume_pdf_path": cand.get("resume_pdf")
                or (existing.resume_pdf_path if existing else None),
                "cover_pdf_path": cand.get("cover_pdf")
                or (existing.cover_pdf_path if existing else None),
                "rejection_reason": attempt.block_reason,
                "channel_id": attempt.channel_id,
                "apply_method": (
                    self.channels.channels[attempt.channel_id].method
                    if attempt.channel_id in self.channels.channels
                    else "unsupported"
                ),
                "submitted_at": attempt.submitted_at,
                "confirmation_verified": attempt.confirmation_verified,
                "confirmation_reference": attempt.confirmation_reference,
                "confirmation_evidence_json": json.dumps(attempt.confirmation_evidence),
                "screening_answers_json": json.dumps(
                    attempt.screening_answers.model_dump() if attempt.screening_answers else {}
                ),
                "checklist_json": json.dumps(
                    attempt.checklist.model_dump() if attempt.checklist else {}
                ),
                "retry_history_json": json.dumps(retry_history),
                "attempt_count": attempt.attempt_number,
                "block_reason": attempt.block_reason,
            }
        )

    def _recruiter_drafts(self, attempts: list[ApplyAttemptResult]) -> list[dict[str, Any]]:
        drafts: list[dict[str, Any]] = []
        for a in attempts:
            if a.outcome not in {ApplyOutcome.APPLIED, ApplyOutcome.SUBMISSION_UNVERIFIED, ApplyOutcome.DRY_RUN}:
                continue
            drafts.append(
                {
                    "application_key": a.application_key,
                    "channel_id": a.channel_id,
                    "status": "draft_only",
                    "auto_sent": False,
                    "subject": "Interest in UAE AI/ML role — Vaishnavi Santoshi Batchu",
                    "body": (
                        "Draft only (not sent). Introduce candidacy for the role, "
                        "note UAE relocation willingness, and that employer sponsorship "
                        "is required. Attach tailored resume when manually sending."
                    ),
                }
            )
        return drafts

    def _sync_sheets(self, report: ApplyReport) -> None:
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
                "channel_id": a.channel_id,
                "confirmation_verified": a.confirmation_verified,
                "confirmation_reference": a.confirmation_reference,
                "submitted_at": a.submitted_at.isoformat() if a.submitted_at else "",
                "block_reason": a.block_reason,
                "attempt_count": a.attempt_count,
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
            if r["status"]
            in {
                "prepared",
                "ats_failed",
                "applied",
                "submission_unverified",
                "dry_run",
                "blocked",
                "skipped_unsupported",
            }
        ]
        rejected = [r for r in app_rows if r["status"] in {"rejected"}]
        dashboard = {
            "run_id": report.run_id,
            "phase": "phase5",
            "applications_confirmed": report.stats.applied,
            "submission_unverified": report.stats.submission_unverified,
            "blocked": report.stats.blocked,
            "dry_run": report.stats.dry_run,
            "live_submission_enabled": report.live_submission_enabled,
            "updated_at": (report.finished_at or utcnow()).isoformat(),
        }
        sync_phase3_workbook(
            self.sheets,
            dashboard=dashboard,
            applications=app_rows,
            today_jobs=today,
            rejected=rejected,
            run_history=[
                {
                    "run_id": report.run_id,
                    "phase": "phase5",
                    "started_at": report.started_at.isoformat(),
                    "finished_at": (report.finished_at or utcnow()).isoformat(),
                    "stats": json.dumps(report.stats.model_dump()),
                }
            ],
            source_health=[],
            model_costs=[],
            recruiter_outreach=report.recruiter_drafts,
        )
