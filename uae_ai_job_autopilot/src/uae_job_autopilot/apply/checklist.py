from __future__ import annotations

from pathlib import Path

from uae_job_autopilot.apply.channels_config import ChannelConfig
from uae_job_autopilot.domain.models import ChecklistItem, PreSubmitChecklist, ScreeningAnswers
from uae_job_autopilot.db.tables import ApplicationRecord


TERMINAL_APPLIED_STATUSES = frozenset({"applied", "submission_unverified"})
# Hard duplicate: already submitted or marked duplicate. CAPTCHA/MFA blocked may retry.
BLOCKING_PRIOR_STATUSES = frozenset({"applied", "submission_unverified", "duplicate"})


def run_pre_submit_checklist(
    *,
    answers: ScreeningAnswers,
    channel_id: str | None,
    channel: ChannelConfig | None,
    existing: ApplicationRecord | None,
    resume_pdf: str | None,
    cover_pdf: str | None,
    ats_passed: bool,
    live_submission_enabled: bool,
    dry_run: bool,
    method_authorized: bool,
) -> PreSubmitChecklist:
    """
    Pre-submit gates: identity, quals/docs, truthful answers present, no prior apply,
    authorized method. Failures block submission (never mark applied).
    """
    items: list[ChecklistItem] = []

    def add(code: str, ok: bool, detail: str) -> None:
        items.append(ChecklistItem(code=code, ok=ok, detail=detail))

    add(
        "identity_present",
        bool(answers.full_name and answers.email),
        f"name={answers.full_name!r} email={answers.email!r}",
    )
    add(
        "truthful_visa_answer",
        answers.requires_employer_sponsorship is True
        and answers.authorized_to_work_without_sponsorship is False,
        "Requires employer sponsorship; will not claim work authorization without it",
    )
    add(
        "truthful_relocation_answer",
        answers.willing_to_relocate_uae is True,
        f"relocation_willing={answers.willing_to_relocate_uae}",
    )
    add(
        "truthful_salary_answer",
        answers.expected_monthly_aed >= answers.expected_monthly_aed_min,
        f"expected_monthly_aed={answers.expected_monthly_aed}",
    )
    add(
        "truthful_notice_answer",
        answers.notice_period_days > 0,
        f"notice_period_days={answers.notice_period_days}",
    )
    add(
        "qualification_answer_present",
        bool(answers.answers_map.get("highest_qualification")),
        "Education answer sourced from verified resume facts",
    )
    add("ats_passed", bool(ats_passed), "ATS gate must pass before apply")

    resume_ok = bool(resume_pdf and Path(resume_pdf).exists())
    cover_ok = bool(cover_pdf and Path(cover_pdf).exists())
    add("resume_pdf_valid", resume_ok, resume_pdf or "missing")
    add("cover_pdf_valid", cover_ok, cover_pdf or "missing")

    prior_status = (existing.status if existing else "") or ""
    already = prior_status in BLOCKING_PRIOR_STATUSES
    add(
        "no_prior_application",
        not already,
        f"prior_status={prior_status or 'none'}",
    )

    channel_ok = channel is not None and bool(channel_id)
    add("channel_allowlisted", channel_ok, channel_id or "no matching allowlisted channel")

    auth_ok = bool(method_authorized and channel and channel.enabled and channel.authorized)
    add(
        "method_authorized",
        auth_ok or dry_run,  # dry-run may proceed to record intended dry_run outcome
        (
            f"enabled={getattr(channel, 'enabled', False)} "
            f"authorized={getattr(channel, 'authorized', False)} "
            f"live_flag={live_submission_enabled} dry_run={dry_run}"
        ),
    )

    if channel and channel.requires_live_submission and not dry_run:
        add(
            "live_submission_flag",
            bool(live_submission_enabled),
            "ENABLE_LIVE_SUBMISSION required for this channel",
        )
    else:
        add("live_submission_flag", True, "not required for this channel/dry-run")

    blocking = [i.code for i in items if not i.ok]
    # In dry_run, allow proceeding past live_submission_flag / method_authorized
    # only when channel is allowlisted — still block on identity/docs/duplicates/ats.
    soft_in_dry = {"live_submission_flag", "method_authorized"}
    hard = [c for c in blocking if not (dry_run and c in soft_in_dry)]
    return PreSubmitChecklist(passed=len(hard) == 0, items=items, blocking_codes=hard)
