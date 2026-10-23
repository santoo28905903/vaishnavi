from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from uae_job_autopilot.apply.channels_config import ChannelConfig
from uae_job_autopilot.domain.models import ApplyAttemptResult, JobPosting, ScreeningAnswers


@dataclass
class ApplyContext:
    job: JobPosting
    application_key: str
    channel_id: str
    channel: ChannelConfig
    answers: ScreeningAnswers
    resume_pdf: str | None
    cover_pdf: str | None
    dry_run: bool
    live_submission_enabled: bool
    attempt_number: int = 1
    scenario: str | None = None  # mock fixtures: success|captcha|mfa|unverified
    extra: dict[str, Any] = field(default_factory=dict)


class ApplyChannel(ABC):
    """Protocol for allowlisted apply adapters."""

    channel_id: str

    @abstractmethod
    def submit(self, ctx: ApplyContext) -> ApplyAttemptResult:
        """Attempt application. Must never bypass CAPTCHA/MFA or invent confirmation."""
