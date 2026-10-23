from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from uae_job_autopilot.config import DEFAULT_DATA_DIR, Settings, get_settings, load_models_config
from uae_job_autopilot.db.tables import make_session_factory
from uae_job_autopilot.discovery.orchestrator import DiscoveryOrchestrator
from uae_job_autopilot.documents.pipeline import Phase3Pipeline
from uae_job_autopilot.domain.enums import MatchDecision
from uae_job_autopilot.domain.models import JobMatchResult, JobPosting
from uae_job_autopilot.matching.pipeline import MatchingPipeline
from uae_job_autopilot.models.costs import CostLedger
from uae_job_autopilot.ops.checkpoints import CheckpointStore
from uae_job_autopilot.ops.cloud_db import (
    DatabaseConfigError,
    assert_persistent_database,
    is_cloud_environment,
    resolve_database_url,
)
from uae_job_autopilot.ops.cost_guard import CostCapExceeded, CostGuard
from uae_job_autopilot.ops.locks import LockNotAcquired, RunLock
from uae_job_autopilot.reporting.gmail import (
    build_daily_report_email,
    build_email_client,
    send_daily_report_with_recovery,
)
from uae_job_autopilot.utils.timeutil import utcnow

logger = logging.getLogger(__name__)


class DailyPipelineResult:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.started_at = utcnow()
        self.finished_at = None
        self.ok = True
        self.stages: dict[str, Any] = {}
        self.failures: list[str] = []
        self.notes: list[str] = []
        self.cost_usd = 0.0
        self.lock_acquired = False
        self.skipped_due_to_lock = False
        self.submission_enabled = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "ok": self.ok,
            "lock_acquired": self.lock_acquired,
            "skipped_due_to_lock": self.skipped_due_to_lock,
            "cost_usd": self.cost_usd,
            "submission_enabled": self.submission_enabled,
            "stages": self.stages,
            "failures": self.failures,
            "notes": self.notes,
        }


class DailyPipeline:
    """
    Cloud-ready daily orchestration:
    discover → evaluate → prepare_docs → report
    with DB lock, checkpoints, retries, and cost caps.
    Never enables live submissions (Phase 5).
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        data_dir: Path | None = None,
        ledger: CostLedger | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.ledger = ledger or CostLedger()
        self._force_cloud_model_routing()

    def _force_cloud_model_routing(self) -> None:
        """Cloud must not depend on local Ollama."""
        if is_cloud_environment(self.settings):
            self.settings.ollama_enabled = False
            # Prefer cloud generative only when keys exist
            if self.settings.groq_api_key or self.settings.gemini_api_key:
                self.settings.enable_cloud_generative = True
            models = load_models_config()
            models.ollama_enabled = False
            self._models = models
        else:
            self._models = load_models_config()

    def run(
        self,
        *,
        dry_run: bool = False,
        resume_run_id: str | None = None,
        skip_lock: bool = False,
    ) -> DailyPipelineResult:
        run_id = resume_run_id or (
            utcnow().strftime("%Y%m%dT%H%M%SZ") + "-daily-" + uuid.uuid4().hex[:8]
        )
        result = DailyPipelineResult(run_id)
        result.submission_enabled = bool(self.settings.enable_live_submission)
        if result.submission_enabled:
            result.notes.append(
                "WARNING: enable_live_submission=true but Phase 5 apply is not implemented; ignored"
            )
            result.submission_enabled = False

        try:
            db_url = resolve_database_url(self.settings)
            if is_cloud_environment(self.settings):
                assert_persistent_database(self.settings)
                result.notes.append("Cloud DB policy: persistent DATABASE_URL validated")
            else:
                result.notes.append(f"Local DB URL scheme allowed: {db_url.split(':', 1)[0]}")
        except DatabaseConfigError as exc:
            if dry_run:
                result.notes.append(f"dry_run: DB validation note — {exc}")
                for stage in ("discover", "evaluate", "prepare_docs", "report"):
                    result.stages[stage] = {"status": "skipped", "dry_run": True}
                result.finished_at = utcnow()
                self._persist_result(result)
                return result
            result.ok = False
            result.failures.append(str(exc))
            result.finished_at = utcnow()
            self._persist_result(result)
            return result

        session_factory = make_session_factory(db_url)
        owner = (
            os.environ.get("GITHUB_RUN_ID")
            or os.environ.get("HOSTNAME")
            or f"local-{uuid.uuid4().hex[:8]}"
        )
        checkpoints = CheckpointStore(session_factory, run_id)
        guard = CostGuard(self.ledger, cap_usd=self.settings.daily_cost_cap_usd)

        lock: RunLock | None = None
        if not skip_lock and not dry_run:
            lock = RunLock(
                session_factory,
                name=self.settings.lock_name,
                owner=str(owner),
                ttl_seconds=self.settings.lock_ttl_seconds,
            )
            try:
                lock.acquire(meta={"run_id": run_id})
                result.lock_acquired = True
            except LockNotAcquired as exc:
                result.ok = False
                result.skipped_due_to_lock = True
                result.failures.append(str(exc))
                result.notes.append("Another daily run holds the concurrency lock")
                result.finished_at = utcnow()
                self._persist_result(result)
                return result

        try:
            if dry_run:
                result.notes.append("dry_run: stages planned only (no live source/model calls)")
                for stage in ("discover", "evaluate", "prepare_docs", "report"):
                    checkpoints.mark(stage, "skipped", payload={"dry_run": True})
                    result.stages[stage] = {"status": "skipped", "dry_run": True}
                result.finished_at = utcnow()
                if lock is not None:
                    lock.release()
                    lock = None
                self._persist_result(result)
                return result

            discovery_payload = self._stage_discover(checkpoints, result, guard)
            eval_payload = self._stage_evaluate(
                checkpoints, result, guard, discovery_payload
            )
            docs_payload = self._stage_prepare_docs(
                checkpoints, result, guard, discovery_payload, eval_payload
            )
            self._stage_report(
                checkpoints, result, discovery_payload, eval_payload, docs_payload
            )
        except CostCapExceeded as exc:
            result.ok = False
            result.failures.append(str(exc))
            logger.error("Cost cap hit: %s", exc)
        except Exception as exc:  # noqa: BLE001
            result.ok = False
            result.failures.append(f"pipeline:{exc}")
            logger.exception("Daily pipeline failed")
        finally:
            result.cost_usd = round(self.ledger.total_cost_usd, 6)
            result.finished_at = utcnow()
            if lock is not None:
                lock.release()
            self._persist_result(result)
        return result

    def _stage_discover(
        self, checkpoints: CheckpointStore, result: DailyPipelineResult, guard: CostGuard
    ) -> dict[str, Any]:
        if checkpoints.is_done("discover"):
            result.notes.append("Resumed: discover already done")
            return checkpoints.load_payload("discover")

        checkpoints.mark("discover", "running")

        @retry(wait=wait_exponential(multiplier=1, min=1, max=20), stop=stop_after_attempt(3), reraise=True)
        def _run():
            orch = DiscoveryOrchestrator(data_dir=self.data_dir)
            return orch.run(dry_run=False)

        try:
            report = _run()
            payload = {
                "discovery_run_id": report.run_id,
                "stats": report.stats.model_dump(),
                "sources_queried": [
                    {"source": h.source, "status": str(h.status), "detail": h.detail}
                    for h in report.sources_queried()
                ],
                "sources_unavailable": [
                    {"source": h.source, "status": str(h.status), "detail": h.detail}
                    for h in report.sources_unavailable()
                ],
                "selected_jobs": [j.model_dump(mode="json") for j in report.selected_jobs],
                "discovery_unavailable": report.stats.sources_attempted == 0,
            }
            checkpoints.mark("discover", "done", payload=payload)
            result.stages["discover"] = {
                "status": "done",
                "stats": payload["stats"],
                "selected": len(payload["selected_jobs"]),
            }
            return payload
        except Exception as exc:  # noqa: BLE001
            checkpoints.mark("discover", "failed", error=str(exc))
            result.stages["discover"] = {"status": "failed", "error": str(exc)}
            result.failures.append(f"discover:{exc}")
            result.ok = False
            return {
                "stats": {},
                "sources_queried": [],
                "sources_unavailable": [],
                "selected_jobs": [],
                "discovery_unavailable": True,
            }

    def _stage_evaluate(
        self,
        checkpoints: CheckpointStore,
        result: DailyPipelineResult,
        guard: CostGuard,
        discovery_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if checkpoints.is_done("evaluate"):
            result.notes.append("Resumed: evaluate already done")
            return checkpoints.load_payload("evaluate")

        checkpoints.mark("evaluate", "running")
        jobs_raw = discovery_payload.get("selected_jobs") or []
        jobs = [JobPosting.model_validate(j) for j in jobs_raw]

        if not jobs:
            payload = {
                "stats": {"jobs_input": 0, "match_pass": 0},
                "passes": [],
                "results": [],
                "jev_configured": bool(self.settings.typesafe_api_key),
            }
            checkpoints.mark("evaluate", "done", payload=payload)
            result.stages["evaluate"] = {"status": "done", "stats": payload["stats"]}
            return payload

        try:
            guard.check(stage="evaluate")
        except CostCapExceeded:
            checkpoints.mark("evaluate", "skipped", error="cost_cap")
            result.stages["evaluate"] = {"status": "skipped", "reason": "cost_cap"}
            raise

        @retry(wait=wait_exponential(multiplier=1, min=1, max=20), stop=stop_after_attempt(2), reraise=True)
        def _run():
            # Share ledger for cost accounting
            pipe = MatchingPipeline(settings=self.settings, ledger=self.ledger)
            return pipe.evaluate_jobs(jobs, dry_run=False)

        try:
            report = _run()
            guard.check(stage="evaluate_after")
            payload = {
                "evaluation_run_id": report.run_id,
                "stats": report.stats.model_dump(),
                "jev_configured": report.jev_configured,
                "passes": [r.model_dump(mode="json") for r in report.passes()],
                "results": [r.model_dump(mode="json") for r in report.results],
            }
            checkpoints.mark("evaluate", "done", payload=payload)
            result.stages["evaluate"] = {
                "status": "done",
                "stats": payload["stats"],
                "passes": len(payload["passes"]),
            }
            return payload
        except Exception as exc:  # noqa: BLE001
            checkpoints.mark("evaluate", "failed", error=str(exc))
            result.stages["evaluate"] = {"status": "failed", "error": str(exc)}
            result.failures.append(f"evaluate:{exc}")
            result.ok = False
            return {"stats": {}, "passes": [], "results": [], "jev_configured": False}

    def _stage_prepare_docs(
        self,
        checkpoints: CheckpointStore,
        result: DailyPipelineResult,
        guard: CostGuard,
        discovery_payload: dict[str, Any],
        eval_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if checkpoints.is_done("prepare_docs"):
            result.notes.append("Resumed: prepare_docs already done")
            return checkpoints.load_payload("prepare_docs")

        checkpoints.mark("prepare_docs", "running")
        passes = eval_payload.get("passes") or []
        matches = [JobMatchResult.model_validate(p) for p in passes]
        # Also persist rejects from evaluation if present
        for r in eval_payload.get("results") or []:
            mr = JobMatchResult.model_validate(r)
            if mr.decision != MatchDecision.PASS:
                matches.append(mr)

        try:
            guard.check(stage="prepare_docs")
        except CostCapExceeded:
            checkpoints.mark("prepare_docs", "skipped", error="cost_cap")
            result.stages["prepare_docs"] = {"status": "skipped", "reason": "cost_cap"}
            raise

        @retry(wait=wait_exponential(multiplier=1, min=1, max=20), stop=stop_after_attempt(2), reraise=True)
        def _run():
            # Force resolved DB URL into settings for Phase3 persistence
            settings = self.settings.model_copy(
                update={"database_url": resolve_database_url(self.settings)}
            )
            p3 = Phase3Pipeline(settings=settings, data_dir=self.data_dir)
            return p3.prepare_documents_for_matches(
                matches,
                send_email=False,  # report stage sends consolidated email
                sync_sheets=True,
                discovery_stats=discovery_payload.get("stats"),
                sources_queried=[s.get("source") for s in discovery_payload.get("sources_queried") or []],
                sources_unavailable=discovery_payload.get("sources_unavailable") or [],
                discovery_unavailable=bool(discovery_payload.get("discovery_unavailable")),
            )

        try:
            report = _run()
            payload = {
                "phase3_run_id": report.run_id,
                "stats": report.stats,
                "failures": report.failures,
                "documents": [
                    {
                        "job_key": d.job_key,
                        "ats": d.ats.combined_score,
                        "ats_passed": d.ats.passed,
                        "resume_pdf": d.resume_pdf,
                    }
                    for d in report.documents
                ],
            }
            checkpoints.mark("prepare_docs", "done", payload=payload)
            result.stages["prepare_docs"] = {"status": "done", "stats": payload["stats"]}
            result.failures.extend(report.failures)
            return payload
        except Exception as exc:  # noqa: BLE001
            checkpoints.mark("prepare_docs", "failed", error=str(exc))
            result.stages["prepare_docs"] = {"status": "failed", "error": str(exc)}
            result.failures.append(f"prepare_docs:{exc}")
            result.ok = False
            return {"stats": {}, "failures": [str(exc)], "documents": []}

    def _stage_report(
        self,
        checkpoints: CheckpointStore,
        result: DailyPipelineResult,
        discovery_payload: dict[str, Any],
        eval_payload: dict[str, Any],
        docs_payload: dict[str, Any],
    ) -> dict[str, Any]:
        if checkpoints.is_done("report"):
            result.notes.append("Resumed: report already done")
            return checkpoints.load_payload("report")

        checkpoints.mark("report", "running")
        discovery_unavailable = bool(discovery_payload.get("discovery_unavailable"))
        zero_jobs = (discovery_payload.get("stats") or {}).get(
            "jobs_selected_for_evaluation", 0
        ) == 0 and not discovery_unavailable

        subject, body = build_daily_report_email(
            discovery_stats=discovery_payload.get("stats"),
            evaluation_stats=eval_payload.get("stats"),
            document_stats=docs_payload.get("stats"),
            sources_queried=[
                s.get("source") for s in (discovery_payload.get("sources_queried") or [])
            ],
            sources_unavailable=discovery_payload.get("sources_unavailable") or [],
            top_links=[
                d.get("resume_pdf") for d in (docs_payload.get("documents") or []) if d.get("resume_pdf")
            ][:5],
            model_cost_usd=self.ledger.total_cost_usd,
            failures=result.failures,
            discovery_unavailable=discovery_unavailable,
            zero_jobs=zero_jobs,
        )
        # Prefer job application URLs when available
        top_job_links = []
        for p in eval_payload.get("passes") or []:
            job = p.get("job") or {}
            if job.get("application_url"):
                top_job_links.append(job["application_url"])
        if top_job_links:
            subject, body = build_daily_report_email(
                discovery_stats=discovery_payload.get("stats"),
                evaluation_stats=eval_payload.get("stats"),
                document_stats=docs_payload.get("stats"),
                sources_queried=[
                    s.get("source") for s in (discovery_payload.get("sources_queried") or [])
                ],
                sources_unavailable=discovery_payload.get("sources_unavailable") or [],
                top_links=top_job_links[:10],
                model_cost_usd=self.ledger.total_cost_usd,
                failures=result.failures,
                discovery_unavailable=discovery_unavailable,
                zero_jobs=zero_jobs,
            )

        email_client = build_email_client(self.settings)
        email_result = send_daily_report_with_recovery(
            email_client,
            to=self.settings.report_to_email,
            subject=subject,
            body=body,
        )
        if email_result.get("status") != "sent":
            result.failures.append(f"email:{email_result.get('error')}")
            result.ok = False

        payload = {
            "email": email_result,
            "subject": subject,
            "checkpoints": checkpoints.all_stages(),
        }
        checkpoints.mark("report", "done", payload=payload)
        result.stages["report"] = {"status": "done", "email": email_result.get("status")}
        return payload

    def _persist_result(self, result: DailyPipelineResult) -> Path:
        out_dir = self.data_dir / "runs"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{result.run_id}.json"
        path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        summary = {
            "run_id": result.run_id,
            "ok": result.ok,
            "cost_usd": result.cost_usd,
            "failures": result.failures,
            "stages": {k: v.get("status") for k, v in result.stages.items()},
            "notes": result.notes,
            "submission_enabled": result.submission_enabled,
        }
        (out_dir / f"{result.run_id}.summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        return path
