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
