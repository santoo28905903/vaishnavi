from __future__ import annotations

from datetime import datetime

from uae_job_autopilot.domain.enums import PublicationTimeConfidence
from uae_job_autopilot.domain.models import JobPosting
from uae_job_autopilot.utils.timeutil import is_within_window


def is_verified_fresh(
    job: JobPosting,
    *,
    now: datetime | None = None,
    window_hours: int = 24,
) -> bool:
    """Only VERIFIED publication timestamps count toward the 24h evaluation set."""
    if job.publication_confidence != PublicationTimeConfidence.VERIFIED:
        return False
    return is_within_window(job.published_at, now=now, window_hours=window_hours)


def partition_by_freshness(
    jobs: list[JobPosting],
    *,
    now: datetime | None = None,
    window_hours: int = 24,
) -> tuple[list[JobPosting], list[JobPosting]]:
    fresh: list[JobPosting] = []
    excluded: list[JobPosting] = []
    for job in jobs:
        if is_verified_fresh(job, now=now, window_hours=window_hours):
            fresh.append(job)
        else:
            excluded.append(job)
    return fresh, excluded
