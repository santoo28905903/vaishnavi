from __future__ import annotations

from uae_job_autopilot.domain.models import JobPosting
from uae_job_autopilot.utils.fingerprint import soft_fingerprint


# Prefer employer-originated ATS over aggregators when soft-matching.
SOURCE_PRIORITY = {
    "greenhouse": 100,
    "lever": 95,
    "ashby": 95,
    "michael_page": 70,
    "jsearch": 40,
    "linkedin_jobs": 30,
    "naukrigulf": 30,
    "indeed_uae": 30,
    "bayt": 30,
    "gulftalent": 30,
}


def deduplicate(jobs: list[JobPosting]) -> tuple[list[JobPosting], int]:
    """Deduplicate by application URL fingerprint and soft employer/title/location."""
    by_url: dict[str, JobPosting] = {}
    soft_index: dict[str, str] = {}  # soft -> url fingerprint key
    duplicates = 0

    def better(a: JobPosting, b: JobPosting) -> JobPosting:
        pa = SOURCE_PRIORITY.get(a.source, 10)
        pb = SOURCE_PRIORITY.get(b.source, 10)
        if pa != pb:
            return a if pa > pb else b
        # Prefer verified publication times
        if a.published_at and not b.published_at:
            return a
        if b.published_at and not a.published_at:
            return b
        return a

    for job in jobs:
        url_key = job.fingerprint
        soft = soft_fingerprint(
            employer=job.employer, title=job.title, location=job.location_raw
        )
        existing_url = by_url.get(url_key)
        if existing_url is not None:
            by_url[url_key] = better(existing_url, job)
            duplicates += 1
            continue
        if soft in soft_index:
            other_key = soft_index[soft]
            by_url[other_key] = better(by_url[other_key], job)
            duplicates += 1
            continue
        by_url[url_key] = job
        soft_index[soft] = url_key

    return list(by_url.values()), duplicates
