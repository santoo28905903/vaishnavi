from __future__ import annotations

from uae_job_autopilot.config import CandidateProfile, load_candidate_profile
from uae_job_autopilot.domain.models import JobPosting, ScreeningAnswers


def build_screening_answers(
    profile: CandidateProfile | None = None,
    *,
    job: JobPosting | None = None,
) -> ScreeningAnswers:
    """
    Build truthful screening answers from the candidate profile.

    Never invent visa status, qualifications, salary, notice, or relocation willingness.
    """
    profile = profile or load_candidate_profile()
    # If sponsorship is required, candidate is NOT authorized to work without sponsorship.
    authorized_without = not bool(profile.requires_employer_sponsorship)
    answers_map = {
        "full_name": profile.full_name,
        "email": profile.email,
        "phone": profile.phone or "",
        "linkedin": profile.linkedin or "",
        "current_location": f"{profile.current_city}, {profile.current_country}",
        "requires_visa_sponsorship": "Yes" if profile.requires_employer_sponsorship else "No",
        "authorized_to_work_without_sponsorship": "Yes" if authorized_without else "No",
        "willing_to_relocate_to_uae": "Yes" if profile.relocation_willing else "No",
        "notice_period_days": str(profile.notice_period_days),
        "expected_monthly_salary_aed": str(int(profile.expected_monthly_aed_default)),
        "expected_salary_range_aed": (
            f"{int(profile.expected_monthly_aed_min)}-{int(profile.expected_monthly_aed_max)}"
        ),
        "years_of_experience": str(profile.total_experience_years_approx),
        "current_title": profile.current_title,
        "highest_qualification": "B.Tech, Data Science & Artificial Intelligence — ICFAI Hyderabad",
    }
    if job is not None:
        answers_map["target_role"] = job.title
        answers_map["target_employer"] = job.employer

    return ScreeningAnswers(
        full_name=profile.full_name,
        email=profile.email,
        phone=profile.phone,
        linkedin=profile.linkedin,
        current_city=profile.current_city,
        current_country=profile.current_country,
        requires_employer_sponsorship=bool(profile.requires_employer_sponsorship),
        willing_to_relocate_uae=bool(profile.relocation_willing),
        notice_period_days=int(profile.notice_period_days),
        expected_monthly_aed=float(profile.expected_monthly_aed_default),
        expected_monthly_aed_min=float(profile.expected_monthly_aed_min),
        expected_monthly_aed_max=float(profile.expected_monthly_aed_max),
        years_experience=float(profile.total_experience_years_approx),
        current_title=profile.current_title,
        authorized_to_work_without_sponsorship=authorized_without,
        answers_map=answers_map,
    )


def answer_field(answers: ScreeningAnswers, field_hint: str) -> str | None:
    """Map a free-text form label/hint to a truthful answer value."""
    hint = (field_hint or "").lower()
    # More specific patterns first (authorized-without-sponsorship before generic visa).
    mapping = [
        (("name", "full name"), answers.full_name),
        (("email", "e-mail"), answers.email),
        (("phone", "mobile", "tel"), answers.phone or ""),
        (("linkedin",), answers.linkedin or ""),
        (("city", "location"), answers.current_city),
        (("country",), answers.current_country),
        (
            ("authorized to work", "legally authorized", "without sponsorship"),
            "No" if answers.requires_employer_sponsorship else "Yes",
        ),
        (
            ("sponsor", "visa", "work authorization", "eligible to work"),
            "Yes — requires employer sponsorship"
            if answers.requires_employer_sponsorship
            else "No sponsorship required",
        ),
        (
            ("relocat", "willing to move"),
            "Yes" if answers.willing_to_relocate_uae else "No",
        ),
        (("notice", "availability", "start date", "when can you"), f"{answers.notice_period_days} days"),
        (
            ("salary", "compensation", "expected pay", "expected ctc"),
            str(int(answers.expected_monthly_aed)),
        ),
        (("experience", "years of"), str(answers.years_experience)),
        (("title", "current role", "current position"), answers.current_title),
        (("qualification", "education", "degree"), answers.answers_map.get("highest_qualification", "")),
    ]
    for keys, value in mapping:
        if any(k in hint for k in keys):
            return value
    return None
