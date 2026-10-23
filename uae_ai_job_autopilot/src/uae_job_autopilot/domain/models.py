from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from uae_job_autopilot.domain.enums import (
    AccessMode,
    ApplicationStatus,
    ApplyOutcome,
    MatchDecision,
    PublicationTimeConfidence,
    SourceStatus,
    SponsorshipLabel,
    VisaEvidenceLabel,
)


class JobPosting(BaseModel):
    """Normalized vacancy from any source adapter."""

    source: str
    source_job_id: str
    title: str
    employer: str
    location_raw: str
    locations_normalized: list[str] = Field(default_factory=list)
    is_uae: bool = False
    application_url: str
    description_text: str | None = None
    salary_raw: str | None = None
    salary_monthly_aed_min: float | None = None
    salary_monthly_aed_max: float | None = None
    published_at: datetime | None = None
    publication_confidence: PublicationTimeConfidence = PublicationTimeConfidence.UNKNOWN
    discovered_at: datetime
    updated_at_source: datetime | None = None
    fingerprint: str = ""
    raw_provenance: dict[str, Any] = Field(default_factory=dict)
    board_or_site: str | None = None


class SourceHealth(BaseModel):
    source: str
    access_mode: AccessMode
    status: SourceStatus
    attempted: bool
    jobs_fetched_raw: int = 0
    jobs_after_uae_filter: int = 0
    jobs_after_freshness: int = 0
    error: str | None = None
    detail: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    http_status: int | None = None


class DiscoveryStats(BaseModel):
    sources_configured: int = 0
    sources_attempted: int = 0
    sources_success: int = 0
    sources_failed: int = 0
    sources_skipped: int = 0
    jobs_raw: int = 0
    jobs_uae: int = 0
    jobs_fresh: int = 0
    jobs_duplicates_removed: int = 0
    jobs_excluded_stale_or_unverifiable: int = 0
    jobs_selected_for_evaluation: int = 0
    jobs_additionally_discovered: int = 0


class DiscoveryReport(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime
    dry_run: bool
    window_hours: int
    evaluation_cap: int
    stats: DiscoveryStats
    source_health: list[SourceHealth]
    selected_jobs: list[JobPosting]
    all_fresh_unique_jobs: list[JobPosting] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def sources_unavailable(self) -> list[SourceHealth]:
        bad = {
            SourceStatus.FAILED,
            SourceStatus.SKIPPED_NOT_CONFIGURED,
            SourceStatus.SKIPPED_UNSUPPORTED,
            SourceStatus.QUOTA_EXHAUSTED,
        }
        return [h for h in self.source_health if h.status in bad]

    def sources_queried(self) -> list[SourceHealth]:
        return [h for h in self.source_health if h.attempted]


class AdapterFetchResult(BaseModel):
    health: SourceHealth
    jobs: list[JobPosting] = Field(default_factory=list)


class ModelUsageRecord(BaseModel):
    provider: str
    model: str
    operation: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cached: bool = False
    error: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class HardExclusion(BaseModel):
    code: str
    reason: str
    authoritative: bool = True


class VisaAssessment(BaseModel):
    deterministic_score: float
    jev_score: float | None = None
    combined_score: float
    threshold: float = 70.0
    passed: bool
    sponsorship_label: SponsorshipLabel = SponsorshipLabel.UNKNOWN
    evidence_label: VisaEvidenceLabel = VisaEvidenceLabel.NEUTRAL
    deterministic_signals: list[str] = Field(default_factory=list)
    jev_raw: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    # Explicit: unknown must never be described as confirmed sponsorship
    sponsorship_confirmed: bool = False


class ResumeFitAssessment(BaseModel):
    embedding_score: float
    rubric_score: float | None = None
    combined_score: float
    threshold: float = 75.0
    passed: bool
    embedding_weight: float = 0.40
    rubric_weight: float = 0.60
    jev_raw: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class JobMatchResult(BaseModel):
    job: JobPosting
    decision: MatchDecision
    hard_exclusions: list[HardExclusion] = Field(default_factory=list)
    resume_fit: ResumeFitAssessment | None = None
    visa: VisaAssessment | None = None
    next_action: str | None = None
    usage: list[ModelUsageRecord] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class EvaluationStats(BaseModel):
    jobs_input: int = 0
    hard_blocked: int = 0
    resume_pass: int = 0
    resume_fail: int = 0
    visa_pass: int = 0
    visa_fail: int = 0
    match_pass: int = 0
    needs_model: int = 0
    model_errors: int = 0
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


class EvaluationReport(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime
    dry_run: bool = False
    jev_configured: bool
    embedding_model: str
    stats: EvaluationStats
    results: list[JobMatchResult] = Field(default_factory=list)
    usage: list[ModelUsageRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def passes(self) -> list[JobMatchResult]:
        return [r for r in self.results if r.decision == MatchDecision.PASS]


class ScreeningAnswers(BaseModel):
    """Truthful application answers derived from CandidateProfile — never fabricated."""

    full_name: str
    email: str
    phone: str | None = None
    linkedin: str | None = None
    current_city: str
    current_country: str
    requires_employer_sponsorship: bool
    willing_to_relocate_uae: bool
    notice_period_days: int
    expected_monthly_aed: float
    expected_monthly_aed_min: float
    expected_monthly_aed_max: float
    years_experience: float
    current_title: str
    authorized_to_work_without_sponsorship: bool = False  # always False when sponsorship required
    answers_map: dict[str, str] = Field(default_factory=dict)
    truthfulness_attestation: str = (
        "Answers are derived from candidate.yaml / resume facts; nothing invented."
    )


class ChecklistItem(BaseModel):
    code: str
    ok: bool
    detail: str


class PreSubmitChecklist(BaseModel):
    passed: bool
    items: list[ChecklistItem] = Field(default_factory=list)
    blocking_codes: list[str] = Field(default_factory=list)


class ApplyAttemptResult(BaseModel):
    application_key: str
    channel_id: str
    outcome: ApplyOutcome
    status: ApplicationStatus
    dry_run: bool = False
    confirmation_verified: bool = False
    confirmation_reference: str | None = None
    confirmation_evidence: dict[str, Any] = Field(default_factory=dict)
    block_reason: str | None = None
    error: str | None = None
    screening_answers: ScreeningAnswers | None = None
    checklist: PreSubmitChecklist | None = None
    uploaded_files: list[str] = Field(default_factory=list)
    attempt_number: int = 1
    submitted_at: datetime | None = None
    notes: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ApplyStats(BaseModel):
    candidates: int = 0
    attempted: int = 0
    applied: int = 0
    dry_run: int = 0
    blocked: int = 0
    submission_unverified: int = 0
    skipped_unsupported: int = 0
    duplicates: int = 0
    checklist_failed: int = 0
    errors: int = 0


class ApplyReport(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    dry_run: bool = False
    live_submission_enabled: bool = False
    stats: ApplyStats = Field(default_factory=ApplyStats)
    attempts: list[ApplyAttemptResult] = Field(default_factory=list)
    recruiter_drafts: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
