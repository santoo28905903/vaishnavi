from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from uae_job_autopilot.apply.answers import answer_field
from uae_job_autopilot.apply.base import ApplyContext
from uae_job_autopilot.domain.enums import ApplicationStatus, ApplyOutcome
from uae_job_autopilot.domain.models import ApplyAttemptResult
from uae_job_autopilot.utils.timeutil import utcnow

CAPTCHA_PATTERNS = (
    r"captcha",
    r"recaptcha",
    r"hcaptcha",
    r"cf-turnstile",
    r"g-recaptcha",
    r"challenge-platform",
)
MFA_PATTERNS = (
    r"two[- ]factor",
    r"\bmfa\b",
    r"authenticator",
    r"verification code",
    r"enter the code",
    r"one[- ]time password",
    r"\botp\b",
)
CONFIRMATION_PATTERNS = (
    r"thank you for appl",
    r"application (has been )?received",
    r"application submitted",
    r"successfully applied",
    r"we('ve| have) received your application",
)


def page_signals(html: str) -> dict[str, bool]:
    text = (html or "").lower()
    return {
        "captcha": any(re.search(p, text) for p in CAPTCHA_PATTERNS),
        "mfa": any(re.search(p, text) for p in MFA_PATTERNS),
        "confirmation": any(re.search(p, text) for p in CONFIRMATION_PATTERNS),
    }


def blocked_result(
    ctx: ApplyContext,
    *,
    channel_id: str,
    reason: str,
    evidence: dict[str, Any] | None = None,
) -> ApplyAttemptResult:
    return ApplyAttemptResult(
        application_key=ctx.application_key,
        channel_id=channel_id,
        outcome=ApplyOutcome.BLOCKED,
        status=ApplicationStatus.BLOCKED,
        dry_run=ctx.dry_run,
        block_reason=reason,
        attempt_number=ctx.attempt_number,
        submitted_at=utcnow(),
        screening_answers=ctx.answers,
        notes=[reason],
        evidence=evidence or {},
    )


def dry_run_result(
    ctx: ApplyContext,
    *,
    channel_id: str,
    notes: list[str],
    evidence: dict[str, Any] | None = None,
) -> ApplyAttemptResult:
    uploaded = [p for p in (ctx.resume_pdf, ctx.cover_pdf) if p and Path(p).exists()]
    return ApplyAttemptResult(
        application_key=ctx.application_key,
        channel_id=channel_id,
        outcome=ApplyOutcome.DRY_RUN,
        status=ApplicationStatus.DRY_RUN,
        dry_run=True,
        confirmation_verified=False,
        uploaded_files=uploaded,
        attempt_number=ctx.attempt_number,
        submitted_at=utcnow(),
        screening_answers=ctx.answers,
        notes=notes,
        evidence=evidence or {"application_url": ctx.job.application_url},
    )


def fill_common_fields(page: Any, ctx: ApplyContext) -> list[str]:
    """Best-effort fill of common input labels using truthful answers. Returns filled labels."""
    filled: list[str] = []
    # Greenhouse / Lever often use name / email / phone / linkedin attributes
    selectors = [
        ('input[name*="name" i], input[id*="name" i], input[autocomplete="name"]', "full name"),
        ('input[type="email"], input[name*="email" i]', "email"),
        ('input[type="tel"], input[name*="phone" i]', "phone"),
        ('input[name*="linkedin" i], input[id*="linkedin" i]', "linkedin"),
    ]
    for sel, hint in selectors:
        value = answer_field(ctx.answers, hint)
        if not value:
            continue
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            loc.fill(value)
            filled.append(hint)
        except Exception:  # noqa: BLE001
            continue

    # Textareas / selects that look like screening questions
    try:
        labels = page.locator("label").all()
        for label in labels[:40]:
            try:
                text = (label.inner_text() or "").strip()
            except Exception:  # noqa: BLE001
                continue
            value = answer_field(ctx.answers, text)
            if not value:
                continue
            try:
                for_id = label.get_attribute("for")
                if for_id:
                    target = page.locator(f"#{for_id}")
                else:
                    target = label.locator("xpath=following::input[1] | following::textarea[1] | following::select[1]")
                if target.count() == 0:
                    continue
                tag = target.first.evaluate("el => el.tagName.toLowerCase()")
                if tag == "select":
                    # Prefer option containing Yes/No when applicable
                    target.first.select_option(label=value)
                else:
                    target.first.fill(value)
                filled.append(text[:80])
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return filled


def upload_documents(page: Any, ctx: ApplyContext) -> list[str]:
    uploaded: list[str] = []
    for path, hints in (
        (ctx.resume_pdf, ("resume", "cv", "curriculum")),
        (ctx.cover_pdf, ("cover", "letter")),
    ):
        if not path or not Path(path).exists():
            continue
        try:
            inputs = page.locator('input[type="file"]').all()
            for inp in inputs:
                name = ((inp.get_attribute("name") or "") + " " + (inp.get_attribute("id") or "")).lower()
                if any(h in name for h in hints) or (hints[0] == "resume" and "cover" not in name):
                    inp.set_input_files(path)
                    uploaded.append(path)
                    break
        except Exception:  # noqa: BLE001
            continue
    return uploaded


def run_playwright_apply(
    ctx: ApplyContext,
    *,
    channel_id: str,
    board_name: str,
) -> ApplyAttemptResult:
    """
    Shared Playwright flow for permitted board form automation.

    Safety:
    - CAPTCHA / MFA → blocked (no bypass)
    - dry_run → fill only, never click submit
    - live → submit then require confirmation markers else submission_unverified
    """
    if ctx.dry_run or not ctx.live_submission_enabled:
        return dry_run_result(
            ctx,
            channel_id=channel_id,
            notes=[
                f"dry_run/safety: would automate {board_name} form at {ctx.job.application_url}",
                "Public discovery APIs do not accept applications; browser path requires live flag",
            ],
            evidence={"board": board_name, "would_live": False},
        )

    if not ctx.channel.enabled or not ctx.channel.authorized:
        return blocked_result(
            ctx,
            channel_id=channel_id,
            reason=f"{board_name} channel not enabled+authorized in application_channels.yaml",
        )

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return blocked_result(
            ctx,
            channel_id=channel_id,
            reason="playwright not installed — cannot run browser automation",
        )

    evidence: dict[str, Any] = {"board": board_name, "url": ctx.job.application_url}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(ctx.job.application_url, wait_until="domcontentloaded", timeout=60000)
            html = page.content()
            signals = page_signals(html)
            evidence["signals_initial"] = signals
            if signals["captcha"] and ctx.channel.block_on_captcha:
                browser.close()
                return blocked_result(
                    ctx,
                    channel_id=channel_id,
                    reason="CAPTCHA detected — blocked (no bypass)",
                    evidence=evidence,
                )
            if signals["mfa"] and ctx.channel.block_on_mfa:
                browser.close()
                return blocked_result(
                    ctx,
                    channel_id=channel_id,
                    reason="MFA / login challenge detected — blocked",
                    evidence=evidence,
                )

            filled = fill_common_fields(page, ctx)
            uploaded = upload_documents(page, ctx)
            evidence["filled_fields"] = filled
            evidence["uploaded"] = uploaded

            # Re-check before submit
            html2 = page.content()
            signals2 = page_signals(html2)
            evidence["signals_pre_submit"] = signals2
            if signals2["captcha"] and ctx.channel.block_on_captcha:
                browser.close()
                return blocked_result(
                    ctx,
                    channel_id=channel_id,
                    reason="CAPTCHA appeared before submit — blocked",
                    evidence=evidence,
                )

            submit = page.locator(
                'button[type="submit"], input[type="submit"], button:has-text("Submit"), '
                'button:has-text("Apply"), button:has-text("Send application")'
            ).first
            if submit.count() == 0:
                browser.close()
                return ApplyAttemptResult(
                    application_key=ctx.application_key,
                    channel_id=channel_id,
                    outcome=ApplyOutcome.SUBMISSION_UNVERIFIED,
                    status=ApplicationStatus.SUBMISSION_UNVERIFIED,
                    dry_run=False,
                    confirmation_verified=False,
                    block_reason=None,
                    uploaded_files=uploaded,
                    attempt_number=ctx.attempt_number,
                    submitted_at=utcnow(),
                    screening_answers=ctx.answers,
                    notes=["No submit control found — cannot verify submission"],
                    evidence=evidence,
                )

            submit.click()
            page.wait_for_timeout(2500)
            final_html = page.content()
            final_url = page.url
            signals_final = page_signals(final_html)
            evidence["final_url"] = final_url
            evidence["signals_final"] = signals_final
            browser.close()

            if signals_final["captcha"] or signals_final["mfa"]:
                return blocked_result(
                    ctx,
                    channel_id=channel_id,
                    reason="CAPTCHA/MFA after submit attempt — blocked; not marked applied",
                    evidence=evidence,
                )

            if signals_final["confirmation"]:
                return ApplyAttemptResult(
                    application_key=ctx.application_key,
                    channel_id=channel_id,
                    outcome=ApplyOutcome.APPLIED,
                    status=ApplicationStatus.APPLIED,
                    dry_run=False,
                    confirmation_verified=True,
                    confirmation_reference=final_url,
                    confirmation_evidence={
                        "final_url": final_url,
                        "confirmation_detected": True,
                    },
                    uploaded_files=uploaded,
                    attempt_number=ctx.attempt_number,
                    submitted_at=utcnow(),
                    screening_answers=ctx.answers,
                    notes=[f"{board_name}: confirmation markers verified"],
                    evidence=evidence,
                )

            return ApplyAttemptResult(
                application_key=ctx.application_key,
                channel_id=channel_id,
                outcome=ApplyOutcome.SUBMISSION_UNVERIFIED,
                status=ApplicationStatus.SUBMISSION_UNVERIFIED,
                dry_run=False,
                confirmation_verified=False,
                confirmation_reference=final_url,
                confirmation_evidence={
                    "final_url": final_url,
                    "confirmation_detected": False,
                },
                uploaded_files=uploaded,
                attempt_number=ctx.attempt_number,
                submitted_at=utcnow(),
                screening_answers=ctx.answers,
                notes=[
                    f"{board_name}: submit clicked but confirmation not verified — "
                    "status submission_unverified (not applied)"
                ],
                evidence=evidence,
            )
    except Exception as exc:  # noqa: BLE001
        return ApplyAttemptResult(
            application_key=ctx.application_key,
            channel_id=channel_id,
            outcome=ApplyOutcome.ERROR,
            status=ApplicationStatus.BLOCKED,
            dry_run=False,
            block_reason=f"browser automation error: {exc}",
            error=str(exc),
            attempt_number=ctx.attempt_number,
            submitted_at=utcnow(),
            screening_answers=ctx.answers,
            notes=[f"error: {exc}"],
            evidence=evidence,
        )
