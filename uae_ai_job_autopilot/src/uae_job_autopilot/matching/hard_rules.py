from __future__ import annotations

import re

from uae_job_autopilot.config import CandidateProfile
from uae_job_autopilot.domain.models import HardExclusion, JobPosting
from uae_job_autopilot.utils.location import is_uae_location

# Explicit sponsorship / nationality blockers — authoritative over numeric scores.
NATIONALS_ONLY = re.compile(
    r"("
    r"emirati\s+national(?:s)?\s+only|"
    r"uae\s+national(?:s)?\s+only|"
    r"only\s+for\s+uae\s+national|"
    r"only\s+emirati|"
    r"emirati\s+nationals?\s+preferred|"
    r"restricted\s+to\s+uae\s+nationals"
    r")",
    re.IGNORECASE,
)

NO_SPONSORSHIP = re.compile(
    r"("
    r"no\s+visa\s+sponsorship|"
    r"visa\s+sponsorship\s+(?:is\s+)?not\s+available|"
    r"must\s+(?:already\s+)?have\s+(?:a\s+)?(?:valid\s+)?(?:uae\s+)?(?:work\s+)?(?:visa|permit)|"
    r"candidates\s+must\s+be\s+(?:based\s+in\s+the\s+uae|uae\s+residents)|"
    r"only\s+(?:candidates\s+)?with\s+(?:existing\s+)?uae\s+(?:visa|residency)"
    r")",
    re.IGNORECASE,
)

CITIZENSHIP_REQUIRED = re.compile(
    r"(must\s+be\s+(?:a\s+)?(?:uae\s+)?citizen|citizenship\s+required)",
    re.IGNORECASE,
)

EXPERIENCE_YEARS = re.compile(
    r"(?P<min>\d+)\s*\+?\s*(?:-|to)?\s*(?P<max>\d+)?\s*\+?\s*years?\s+(?:of\s+)?(?:experience|exp)",
    re.IGNORECASE,
)

MIN_YEARS = re.compile(
    r"(?:minimum|at\s+least|min\.?)\s+(?P<min>\d+)\s*\+?\s*years?",
    re.IGNORECASE,
)


def evaluate_hard_exclusions(
    job: JobPosting,
    profile: CandidateProfile,
) -> list[HardExclusion]:
    """Deterministic blockers. Explicit sponsorship/nationality rules are authoritative."""
    exclusions: list[HardExclusion] = []
    blob = " ".join(
        filter(
            None,
            [job.title, job.employer, job.location_raw, job.description_text or ""],
        )
    )

    if not is_uae_location(job.location_raw) and not job.is_uae:
        exclusions.append(
            HardExclusion(
                code="location_not_uae",
                reason=f"Location not UAE: {job.location_raw!r}",
            )
        )

    # Salary: reject only when verified maximum monthly compensation is below floor.
    if (
        job.salary_monthly_aed_max is not None
        and job.salary_monthly_aed_max < profile.hard_floor_monthly_aed
    ):
        exclusions.append(
            HardExclusion(
                code="salary_below_floor",
                reason=(
                    f"Verified max monthly AED {job.salary_monthly_aed_max:.0f} "
                    f"below hard floor {profile.hard_floor_monthly_aed:.0f}"
                ),
            )
        )

    if NATIONALS_ONLY.search(blob):
        exclusions.append(
            HardExclusion(
                code="emirati_nationals_only",
                reason="Posting restricts role to UAE/Emirati nationals",
                authoritative=True,
            )
        )

    if NO_SPONSORSHIP.search(blob) or CITIZENSHIP_REQUIRED.search(blob):
        if profile.requires_employer_sponsorship:
            exclusions.append(
                HardExclusion(
                    code="no_visa_sponsorship",
                    reason="Explicit no-sponsorship / existing UAE status required",
                    authoritative=True,
                )
            )

    # Experience: only hard-block when mandatory minimum clearly exceeds candidate+buffer.
    years = _extract_min_years(blob)
    if years is not None and years > profile.total_experience_years_approx + 2:
        exclusions.append(
            HardExclusion(
                code="experience_gap",
                reason=(
                    f"Mandatory experience ~{years}+ years exceeds candidate "
                    f"~{profile.total_experience_years_approx} years (+2 buffer)"
                ),
            )
        )

    return exclusions


def _extract_min_years(text: str) -> int | None:
    mins: list[int] = []
    for m in EXPERIENCE_YEARS.finditer(text):
        try:
            mins.append(int(m.group("min")))
        except (TypeError, ValueError):
            continue
    for m in MIN_YEARS.finditer(text):
        try:
            mins.append(int(m.group("min")))
        except (TypeError, ValueError):
            continue
    return max(mins) if mins else None
