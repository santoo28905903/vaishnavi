from __future__ import annotations

from uae_job_autopilot.apply.base import ApplyChannel, ApplyContext
from uae_job_autopilot.domain.enums import ApplicationStatus, ApplyOutcome
from uae_job_autopilot.domain.models import ApplyAttemptResult
from uae_job_autopilot.utils.timeutil import utcnow


class UnsupportedChannel(ApplyChannel):
    """Honest refusal — never pretend an unsupported board accepts automated submissions."""

    def __init__(self, channel_id: str = "unsupported") -> None:
        self.channel_id = channel_id

    def submit(self, ctx: ApplyContext) -> ApplyAttemptResult:
        reason = (
            f"Channel '{self.channel_id}' / source '{ctx.job.source}' is not allowlisted "
            "for automated application. Discovery APIs ≠ apply permission. "
            "No bypass or fabricated submission."
        )
        return ApplyAttemptResult(
            application_key=ctx.application_key,
            channel_id=self.channel_id,
            outcome=ApplyOutcome.SKIPPED_UNSUPPORTED,
            status=ApplicationStatus.SKIPPED_UNSUPPORTED,
            dry_run=ctx.dry_run,
            block_reason=reason,
            submitted_at=utcnow(),
            notes=[reason],
            evidence={"application_url": ctx.job.application_url, "source": ctx.job.source},
        )
