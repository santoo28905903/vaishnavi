from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from uae_job_autopilot.config import DEFAULT_CONFIG_DIR, _load_yaml


class ChannelConfig(BaseModel):
    enabled: bool = False
    authorized: bool = False
    method: str = "unsupported"
    description: str = ""
    url_patterns: list[str] = Field(default_factory=list)
    supports_file_upload: bool = False
    requires_browser: bool = False
    requires_live_submission: bool = True
    block_on_captcha: bool = True
    block_on_mfa: bool = True
    scenarios_dir: str | None = None


class ApplicationChannelsConfig(BaseModel):
    defaults: dict[str, Any] = Field(default_factory=dict)
    channels: dict[str, ChannelConfig] = Field(default_factory=dict)
    unsupported_boards: list[str] = Field(default_factory=list)
    recruiter_outreach: dict[str, Any] = Field(default_factory=dict)

    def max_attempts(self) -> int:
        return int(self.defaults.get("max_attempts_per_job") or 2)

    def resolve_channel_id(self, *, application_url: str, source: str) -> str | None:
        """Return allowlisted channel id matching URL pattern, else None."""
        url = (application_url or "").lower()
        source_l = (source or "").lower()
        for channel_id, cfg in self.channels.items():
            for pattern in cfg.url_patterns:
                if pattern.lower() in url:
                    return channel_id
        # Source named as unsupported board → explicit None (caller marks skipped)
        if source_l in {b.lower() for b in self.unsupported_boards}:
            return None
        return None

    def is_unsupported_source(self, source: str) -> bool:
        return (source or "").lower() in {b.lower() for b in self.unsupported_boards}


def load_application_channels(config_dir: Path | None = None) -> ApplicationChannelsConfig:
    config_dir = config_dir or DEFAULT_CONFIG_DIR
    path = config_dir / "application_channels.yaml"
    raw = _load_yaml(path)
    channels: dict[str, ChannelConfig] = {}
    for name, cfg in (raw.get("channels") or {}).items():
        if isinstance(cfg, dict):
            channels[name] = ChannelConfig.model_validate(cfg)
    return ApplicationChannelsConfig(
        defaults=dict(raw.get("defaults") or {}),
        channels=channels,
        unsupported_boards=list(raw.get("unsupported_boards") or []),
        recruiter_outreach=dict(raw.get("recruiter_outreach") or {}),
    )


def dump_channels_summary(cfg: ApplicationChannelsConfig) -> dict[str, Any]:
    return {
        "channels": {
            k: {
                "enabled": v.enabled,
                "authorized": v.authorized,
                "method": v.method,
                "requires_live_submission": v.requires_live_submission,
            }
            for k, v in cfg.channels.items()
        },
        "unsupported_boards": list(cfg.unsupported_boards),
    }
