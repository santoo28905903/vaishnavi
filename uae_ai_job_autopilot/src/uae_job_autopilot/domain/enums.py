from enum import StrEnum


class SourceStatus(StrEnum):
    """Outcome of a source adapter attempt for one run."""

    SUCCESS = "success"
    EMPTY = "empty"  # ran successfully, zero jobs matched filters
    FAILED = "failed"
    SKIPPED_DISABLED = "skipped_disabled"
    SKIPPED_NOT_CONFIGURED = "skipped_not_configured"
    SKIPPED_UNSUPPORTED = "skipped_unsupported"
    QUOTA_EXHAUSTED = "quota_exhausted"


class PublicationTimeConfidence(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    UNKNOWN = "unknown"


class AccessMode(StrEnum):
    PUBLIC_API = "public_api"
    LICENSED_API = "licensed_api"
    ALERT_INGESTION = "alert_ingestion"
    UNSUPPORTED = "unsupported"


class MatchDecision(StrEnum):
    PASS = "pass"
    REJECT = "reject"
    BLOCKED = "blocked"  # hard exclusion / explicit sponsorship blocker
    NEEDS_MODEL = "needs_model"  # deterministic insufficient; model unavailable
    SKIPPED = "skipped"


class SponsorshipLabel(StrEnum):
    SPONSORS = "sponsors"
    NO_SPONSORSHIP = "no_sponsorship"
    NATIONALS_ONLY = "nationals_only"
    UNCLEAR = "unclear"
    UNKNOWN = "unknown"  # never treat as confirmed sponsorship


class VisaEvidenceLabel(StrEnum):
    STRONG_POSITIVE = "strong_positive"
    WEAK_POSITIVE = "weak_positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    BLOCKER = "blocker"


class ApplicationStatus(StrEnum):
    """Lifecycle status for a tracked application row."""

    PREPARED = "prepared"
    ATS_FAILED = "ats_failed"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    DRY_RUN = "dry_run"
    APPLIED = "applied"
    SUBMISSION_UNVERIFIED = "submission_unverified"
    SKIPPED_UNSUPPORTED = "skipped_unsupported"
    DUPLICATE = "duplicate"


class ApplyOutcome(StrEnum):
    """Result of one apply-channel attempt."""

    APPLIED = "applied"
    DRY_RUN = "dry_run"
    BLOCKED = "blocked"
    SUBMISSION_UNVERIFIED = "submission_unverified"
    SKIPPED_UNSUPPORTED = "skipped_unsupported"
    DUPLICATE = "duplicate"
    CHECKLIST_FAILED = "checklist_failed"
    ERROR = "error"
