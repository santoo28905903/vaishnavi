from __future__ import annotations

from uae_job_autopilot.apply.base import ApplyChannel, ApplyContext
from uae_job_autopilot.apply.channels.browser_common import run_playwright_apply
from uae_job_autopilot.domain.models import ApplyAttemptResult


class GreenhouseBrowserChannel(ApplyChannel):
    """
    Permitted Greenhouse board *form* automation via Playwright when explicitly authorized.

    Honest limits:
    - boards-api.greenhouse.io is discovery-only (no application submit).
    - Harvest Job Board API apply requires employer credentials — not claimed here.
    - CAPTCHA/MFA → blocked; unverified confirmation → submission_unverified.
    """

    channel_id = "greenhouse_browser"

    def submit(self, ctx: ApplyContext) -> ApplyAttemptResult:
        return run_playwright_apply(ctx, channel_id=self.channel_id, board_name="Greenhouse")
