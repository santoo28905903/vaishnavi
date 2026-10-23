from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from uae_job_autopilot.domain.enums import PublicationTimeConfidence
from uae_job_autopilot.domain.models import JobPosting
from uae_job_autopilot.utils.fingerprint import job_fingerprint
from uae_job_autopilot.utils.location import is_uae_location, normalize_locations
from uae_job_autopilot.utils.timeutil import utcnow


def build_job(
    *,
    source: str,
    source_job_id: str,
    title: str,
    employer: str,
    location_raw: str,
    application_url: str,
    discovered_at: datetime | None = None,
    published_at: datetime | None = None,
    publication_confidence: PublicationTimeConfidence = PublicationTimeConfidence.UNKNOWN,
    updated_at_source: datetime | None = None,
    description_text: str | None = None,
    salary_raw: str | None = None,
    salary_monthly_aed_min: float | None = None,
    salary_monthly_aed_max: float | None = None,
    board_or_site: str | None = None,
    raw_provenance: dict[str, Any] | None = None,
) -> JobPosting:
    discovered = discovered_at or utcnow()
    locs = normalize_locations(location_raw)
    uae = is_uae_location(location_raw)
    fp = job_fingerprint(
        employer=employer,
        title=title,
        location=location_raw,
        source_job_id=f"{source}:{source_job_id}",
        application_url=application_url,
    )
    return JobPosting(
        source=source,
        source_job_id=str(source_job_id),
        title=title.strip(),
        employer=employer.strip() or "Unknown",
        location_raw=location_raw.strip(),
        locations_normalized=locs,
        is_uae=uae,
        application_url=application_url.strip(),
        description_text=description_text,
        salary_raw=salary_raw,
        salary_monthly_aed_min=salary_monthly_aed_min,
        salary_monthly_aed_max=salary_monthly_aed_max,
        published_at=published_at,
        publication_confidence=publication_confidence,
        discovered_at=discovered,
        updated_at_source=updated_at_source,
        fingerprint=fp,
        raw_provenance=raw_provenance or {},
        board_or_site=board_or_site,
    )


_GENERIC_TITLE_TOKENS = frozenset(
    {
        "senior",
        "junior",
        "lead",
        "staff",
        "principal",
        "manager",
        "director",
        "head",
        "associate",
        "specialist",
        "analyst",
        "engineer",  # alone too broad (backend/devops/etc.)
        "developer",
        "program",
        "remote",
        "based",
        "fully",
        "and",
        "the",
        "for",
        "with",
    }
)

_STRONG_TITLE_PHRASES = (
    "data scientist",
    "machine learning",
    "deep learning",
    "artificial intelligence",
    "generative ai",
    "agentic",
    "llm",
    "mlops",
    "nlp",
    "computer vision",
    "applied scientist",
    "ai engineer",
    "ml engineer",
    "forward deployed",
    "rag engineer",
    "research scientist",
    "applied ai",
    "genai",
    "gen ai",
)


def title_matches_profile(title: str, keywords: list[str] | None = None) -> bool:
    """Soft relevance gate for large boards; not a Phase 2 match score.

    Requires explicit AI/ML signals. Generic words like ``senior`` / ``engineer``
    alone must not match risk/legal/ops roles.
    """
    del keywords  # reserved for future weighted matching; strong phrases are authoritative
    t = title.lower()
    if any(s in t for s in _STRONG_TITLE_PHRASES):
        return True

    tokens = set(re.findall(r"[a-z0-9]+", t))
    # Whole-token AI/ML markers
    ai_tokens = {"ai", "ml", "llm", "rag", "nlp", "mlops", "genai"}
    if tokens & ai_tokens:
        # Require a role token so random "AI" product marketing titles can still pass,
        # but bare noise is limited.
        roleish = {"engineer", "scientist", "researcher", "architect", "specialist"}
        return bool(tokens & roleish)

    # Multi-token: "machine"+"learning" or "data"+"scientist"
    if {"machine", "learning"} <= tokens:
        return True
    if {"data", "scientist"} <= tokens:
        return True
    if {"deep", "learning"} <= tokens:
        return True
    if {"artificial", "intelligence"} <= tokens:
        return True
    if {"forward", "deployed"} <= tokens:
        return True
    return False
