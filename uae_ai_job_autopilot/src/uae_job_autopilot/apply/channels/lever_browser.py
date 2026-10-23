from __future__ import annotations

from uae_job_autopilot.apply.base import ApplyChannel, ApplyContext
from uae_job_autopilot.apply.channels.browser_common import run_playwright_apply
from uae_job_autopilot.domain.models import ApplyAttemptResult


class LeverBrowserChannel(ApplyChannel):
    """
    Permitted Lever posting form automation via Playwright when explicitly authorized.

    Public api.lever.co is discovery-only and does not accept candidate applications.
    CAPTCHA/MFA → blocked; unverified confirmation → submission_unverified.
    """

    channel_id = "lever_browser"

    def submit(self, ctx: ApplyContext) -> ApplyAttemptResult:
        return run_playwright_apply(ctx, channel_id=self.channel_id, board_name="Lever")
