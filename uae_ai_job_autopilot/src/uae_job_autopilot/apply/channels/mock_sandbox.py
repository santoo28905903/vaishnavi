from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from uae_job_autopilot.apply.base import ApplyChannel, ApplyContext
from uae_job_autopilot.config import PACKAGE_ROOT
from uae_job_autopilot.domain.enums import ApplicationStatus, ApplyOutcome
from uae_job_autopilot.domain.models import ApplyAttemptResult
from uae_job_autopilot.utils.timeutil import utcnow


def _resolve_scenario(ctx: ApplyContext) -> str:
    if ctx.scenario:
        return ctx.scenario
    prov = ctx.job.raw_provenance or {}
    if isinstance(prov.get("mock_scenario"), str):
        return prov["mock_scenario"]
    url = ctx.job.application_url or ""
    if "scenario=" in url:
        return url.split("scenario=", 1)[1].split("&", 1)[0]
    return "success"


def _load_fixture(scenario: str) -> dict[str, Any]:
    path = PACKAGE_ROOT / "tests" / "fixtures" / "apply" / f"{scenario}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    # Built-in defaults when fixture file missing
    defaults: dict[str, dict[str, Any]] = {
        "success": {
            "outcome": "applied",
            "confirmation_verified": True,
            "confirmation_text": "Thank you for applying. Application received.",
            "confirmation_reference_prefix": "MOCK-",
        },
        "captcha": {
            "outcome": "blocked",
            "block_reason": "CAPTCHA challenge detected — automated solve is prohibited",
            "signals": ["captcha", "recaptcha"],
        },
        "mfa": {
            "outcome": "blocked",
            "block_reason": "MFA / login challenge detected — blocked",
            "signals": ["mfa", "two-factor"],
        },
        "unverified": {
            "outcome": "submission_unverified",
            "confirmation_verified": False,
            "confirmation_text": "Form POST returned 200 without confirmation page",
            "notes": ["Submitted to mock endpoint but confirmation markers absent"],
        },
    }
    return defaults.get(scenario, defaults["success"])


class MockSandboxChannel(ApplyChannel):
    """
    Controlled in-process mock ATS for Phase 5 tests.

    Scenarios: success | captcha | mfa | unverified
    Never claims a real employer board accepted the application.
    """

    channel_id = "mock_sandbox"

    def submit(self, ctx: ApplyContext) -> ApplyAttemptResult:
        scenario = _resolve_scenario(ctx)
        fixture = _load_fixture(scenario)
        uploaded: list[str] = []
        for path in (ctx.resume_pdf, ctx.cover_pdf):
            if path and Path(path).exists():
                uploaded.append(path)

        now = utcnow()
        base_evidence = {
            "scenario": scenario,
            "fixture": fixture,
            "mock": True,
            "answers_snapshot": ctx.answers.answers_map,
            "application_url": ctx.job.application_url,
        }

        if ctx.dry_run:
            return ApplyAttemptResult(
                application_key=ctx.application_key,
                channel_id=self.channel_id,
                outcome=ApplyOutcome.DRY_RUN,
                status=ApplicationStatus.DRY_RUN,
                dry_run=True,
                confirmation_verified=False,
                uploaded_files=uploaded,
                attempt_number=ctx.attempt_number,
                submitted_at=now,
                screening_answers=ctx.answers,
                notes=[f"dry_run: would submit mock scenario={scenario}"],
                evidence=base_evidence,
            )

        outcome_raw = str(fixture.get("outcome") or "applied")
        if outcome_raw == "blocked":
            return ApplyAttemptResult(
                application_key=ctx.application_key,
                channel_id=self.channel_id,
                outcome=ApplyOutcome.BLOCKED,
                status=ApplicationStatus.BLOCKED,
                dry_run=False,
                block_reason=str(fixture.get("block_reason") or "blocked by mock scenario"),
                uploaded_files=uploaded,
                attempt_number=ctx.attempt_number,
                submitted_at=now,
                screening_answers=ctx.answers,
                notes=[f"mock blocked scenario={scenario}"],
                evidence={**base_evidence, "signals": fixture.get("signals") or []},
            )

        if outcome_raw == "submission_unverified":
            return ApplyAttemptResult(
                application_key=ctx.application_key,
                channel_id=self.channel_id,
                outcome=ApplyOutcome.SUBMISSION_UNVERIFIED,
                status=ApplicationStatus.SUBMISSION_UNVERIFIED,
                dry_run=False,
                confirmation_verified=False,
                confirmation_reference=None,
                confirmation_evidence={
                    "text": fixture.get("confirmation_text"),
                    "verified": False,
                },
                uploaded_files=uploaded,
                attempt_number=ctx.attempt_number,
                submitted_at=now,
                screening_answers=ctx.answers,
                notes=list(fixture.get("notes") or ["confirmation not verified"]),
                evidence=base_evidence,
            )

        # success → applied only with verified confirmation
        ref = f"{fixture.get('confirmation_reference_prefix', 'MOCK-')}{uuid4().hex[:10].upper()}"
        return ApplyAttemptResult(
            application_key=ctx.application_key,
            channel_id=self.channel_id,
            outcome=ApplyOutcome.APPLIED,
            status=ApplicationStatus.APPLIED,
            dry_run=False,
            confirmation_verified=True,
            confirmation_reference=ref,
            confirmation_evidence={
                "text": fixture.get("confirmation_text"),
                "verified": True,
                "reference": ref,
            },
            uploaded_files=uploaded,
            attempt_number=ctx.attempt_number,
            submitted_at=now,
            screening_answers=ctx.answers,
            notes=[f"mock applied scenario={scenario}"],
            evidence=base_evidence,
        )
