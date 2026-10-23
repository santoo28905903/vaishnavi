from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Iterable

from uae_job_autopilot.config import (
    DEFAULT_DATA_DIR,
    CandidateProfile,
    ModelsConfig,
    Settings,
    get_settings,
    load_models_config,
)
from uae_job_autopilot.domain.enums import MatchDecision, SponsorshipLabel
from uae_job_autopilot.domain.models import (
    EvaluationReport,
    EvaluationStats,
    JobMatchResult,
    JobPosting,
)
from uae_job_autopilot.matching.hard_rules import evaluate_hard_exclusions
from uae_job_autopilot.matching.resume import candidate_state_for_jev, load_parsed_resume
from uae_job_autopilot.matching.scoring import (
    combine_resume_fit,
    compute_embedding_score,
    rubric_from_jev_answers,
)
from uae_job_autopilot.matching.visa import combine_visa_assessment
from uae_job_autopilot.models.costs import CostLedger
from uae_job_autopilot.models.embeddings import EmbeddingService
from uae_job_autopilot.models.jev import JevClient, JevNotConfiguredError
from uae_job_autopilot.utils.timeutil import utcnow

logger = logging.getLogger(__name__)


class MatchingPipeline:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        models: ModelsConfig | None = None,
        profile: CandidateProfile | None = None,
        jev: JevClient | None = None,
        embeddings: EmbeddingService | None = None,
        ledger: CostLedger | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.models = models or load_models_config()
        self.ledger = ledger or CostLedger()
        self.profile = profile or load_parsed_resume()
        self.jev = jev or JevClient(settings=self.settings, models=self.models, ledger=self.ledger)
        self.embeddings = embeddings or EmbeddingService(models=self.models, ledger=self.ledger)
        self.data_dir = data_dir or DEFAULT_DATA_DIR

    def evaluate_jobs(
        self,
        jobs: Iterable[JobPosting],
        *,
        dry_run: bool = False,
    ) -> EvaluationReport:
        started = utcnow()
        run_id = started.strftime("%Y%m%dT%H%M%SZ") + "-match-" + uuid.uuid4().hex[:8]
        results: list[JobMatchResult] = []
        notes: list[str] = []
        stats = EvaluationStats()

        job_list = list(jobs)
        stats.jobs_input = len(job_list)

        if dry_run:
            notes.append("dry_run: matching not executed against models")
            finished = utcnow()
            return EvaluationReport(
                run_id=run_id,
                started_at=started,
                finished_at=finished,
                dry_run=True,
                jev_configured=self.jev.configured,
                embedding_model=self.models.embedding_model,
                stats=stats,
                results=[],
                usage=[],
                notes=notes,
            )

        if not self.jev.configured:
            notes.append(
                "TYPESAFE_API_KEY missing — Jev decisions unavailable; "
                "hard rules + embeddings still applied"
            )

        for job in job_list:
            results.append(self._evaluate_one(job, stats=stats, notes=notes))

        stats.total_cost_usd = round(self.ledger.total_cost_usd, 6)
        stats.total_input_tokens = self.ledger.total_input_tokens
        stats.total_output_tokens = self.ledger.total_output_tokens

        finished = utcnow()
        report = EvaluationReport(
            run_id=run_id,
            started_at=started,
            finished_at=finished,
            dry_run=False,
            jev_configured=self.jev.configured,
            embedding_model=self.models.embedding_model,
            stats=stats,
            results=results,
            usage=list(self.ledger.records),
            notes=notes,
        )
        self._persist(report)
        return report

    def _evaluate_one(
        self,
        job: JobPosting,
        *,
        stats: EvaluationStats,
        notes: list[str],
    ) -> JobMatchResult:
        hard = evaluate_hard_exclusions(job, self.profile)
        if hard:
            stats.hard_blocked += 1
            visa = combine_visa_assessment(
                job,
                self.profile,
                self.models,
                hard_blocked=any(
                    h.code in {"emirati_nationals_only", "no_visa_sponsorship"} for h in hard
                ),
            )
            return JobMatchResult(
                job=job,
                decision=MatchDecision.BLOCKED,
                hard_exclusions=hard,
                visa=visa,
                next_action="reject",
                evidence={"hard_exclusions": [h.model_dump() for h in hard]},
            )

        # Embeddings always (local)
        emb_score = compute_embedding_score(self.profile, job, self.embeddings)

        jev_payload: dict | None = None
        usage_before = len(self.ledger.records)
        try:
            if self.jev.configured:
                jev_payload = self.jev.job_decision_bundle(
                    job_state=_job_state(job),
                    candidate_state=candidate_state_for_jev(self.profile),
                )
            else:
                stats.needs_model += 1
        except JevNotConfiguredError:
            stats.needs_model += 1
        except Exception as exc:  # noqa: BLE001
            stats.model_errors += 1
            notes.append(f"Jev error for {job.source}:{job.source_job_id}: {exc}")
            logger.exception("Jev evaluation failed")

        answers = (jev_payload or {}).get("answers") or {}
        rubric, rubric_meta = rubric_from_jev_answers(answers)
        resume_fit = combine_resume_fit(
            embedding_score=emb_score,
            rubric_score=rubric,
            models=self.models,
            jev_raw={"answers": answers, "rubric_meta": rubric_meta},
        )
        if resume_fit.passed:
            stats.resume_pass += 1
        else:
            stats.resume_fail += 1

        visa_answer = answers.get("visa_evidence") if answers else None
        visa = combine_visa_assessment(
            job,
            self.profile,
            self.models,
            jev_answer=visa_answer if isinstance(visa_answer, dict) else None,
        )
        if visa.passed:
            stats.visa_pass += 1
        else:
            stats.visa_fail += 1

        # Authoritative sponsorship blockers even if numeric visa somehow passed
        if visa.sponsorship_label in {
            SponsorshipLabel.NATIONALS_ONLY,
            SponsorshipLabel.NO_SPONSORSHIP,
        }:
            decision = MatchDecision.BLOCKED
            next_action = "reject"
        elif rubric is None and not self.jev.configured:
            decision = MatchDecision.NEEDS_MODEL
            next_action = "hold_review"
        elif resume_fit.passed and visa.passed:
            decision = MatchDecision.PASS
            next_action = (answers.get("next_action") or {}).get("choice") or "advance"
            stats.match_pass += 1
        else:
            decision = MatchDecision.REJECT
            next_action = "reject"

        return JobMatchResult(
            job=job,
            decision=decision,
            hard_exclusions=[],
            resume_fit=resume_fit,
            visa=visa,
            next_action=next_action,
            usage=list(self.ledger.records[usage_before:]),
            evidence={
                "sponsorship_confirmed": visa.sponsorship_confirmed,
                "jev_model": (jev_payload or {}).get("model"),
            },
        )

    def _persist(self, report: EvaluationReport) -> Path:
        out_dir = self.data_dir / "runs"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{report.run_id}.json"
        path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        summary = {
            "run_id": report.run_id,
            "stats": report.stats.model_dump(),
            "jev_configured": report.jev_configured,
            "embedding_model": report.embedding_model,
            "passes": [
                {
                    "title": r.job.title,
                    "employer": r.job.employer,
                    "url": r.job.application_url,
                    "resume_score": r.resume_fit.combined_score if r.resume_fit else None,
                    "visa_score": r.visa.combined_score if r.visa else None,
                    "sponsorship_label": r.visa.sponsorship_label if r.visa else None,
                    "sponsorship_confirmed": r.visa.sponsorship_confirmed if r.visa else False,
                }
                for r in report.passes()
            ],
            "blocked_or_rejected": [
                {
                    "title": r.job.title,
                    "decision": r.decision,
                    "hard": [h.code for h in r.hard_exclusions],
                    "resume": r.resume_fit.combined_score if r.resume_fit else None,
                    "visa": r.visa.combined_score if r.visa else None,
                }
                for r in report.results
                if r.decision != MatchDecision.PASS
            ],
            "notes": report.notes,
            "total_cost_usd": report.stats.total_cost_usd,
        }
        summary_path = out_dir / f"{report.run_id}.summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        return path


def _job_state(job: JobPosting) -> dict:
    return {
        "title": job.title,
        "employer": job.employer,
        "location": job.location_raw,
        "application_url": job.application_url,
        "salary_raw": job.salary_raw,
        "salary_monthly_aed_min": job.salary_monthly_aed_min,
        "salary_monthly_aed_max": job.salary_monthly_aed_max,
        "description": (job.description_text or "")[:6000],
        "source": job.source,
        "source_job_id": job.source_job_id,
    }
