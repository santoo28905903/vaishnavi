from __future__ import annotations

from uae_job_autopilot.apply.base import ApplyChannel
from uae_job_autopilot.apply.channels.greenhouse_browser import GreenhouseBrowserChannel
from uae_job_autopilot.apply.channels.lever_browser import LeverBrowserChannel
from uae_job_autopilot.apply.channels.mock_sandbox import MockSandboxChannel
from uae_job_autopilot.apply.channels.unsupported import UnsupportedChannel

CHANNEL_REGISTRY: dict[str, type[ApplyChannel]] = {
    "mock_sandbox": MockSandboxChannel,
    "greenhouse_browser": GreenhouseBrowserChannel,
    "lever_browser": LeverBrowserChannel,
}


def build_channel(channel_id: str) -> ApplyChannel:
    cls = CHANNEL_REGISTRY.get(channel_id)
    if cls is None:
        return UnsupportedChannel(channel_id=channel_id)
    return cls()


__all__ = [
    "CHANNEL_REGISTRY",
    "build_channel",
    "MockSandboxChannel",
    "GreenhouseBrowserChannel",
    "LeverBrowserChannel",
    "UnsupportedChannel",
]
