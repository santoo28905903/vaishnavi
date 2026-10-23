from __future__ import annotations

from uae_job_autopilot.config import SourceConfig
from uae_job_autopilot.domain.enums import AccessMode, SourceStatus
from uae_job_autopilot.domain.models import AdapterFetchResult, SourceHealth
from uae_job_autopilot.utils.timeutil import utcnow


def skipped_result(
    *,
    source: str,
    access_mode: AccessMode,
    status: SourceStatus,
    detail: str,
    source_cfg: SourceConfig | None = None,
) -> AdapterFetchResult:
    now = utcnow()
    return AdapterFetchResult(
        health=SourceHealth(
            source=source,
            access_mode=access_mode,
            status=status,
            attempted=False,
            detail=detail or (source_cfg.detail if source_cfg else None),
            started_at=now,
            finished_at=now,
        ),
        jobs=[],
    )


def require_enabled(
    *,
    source: str,
    access_mode: AccessMode,
    source_cfg: SourceConfig,
    env_value: str | None = None,
    requires_env: str | None = None,
) -> AdapterFetchResult | None:
    if not source_cfg.enabled:
        return skipped_result(
            source=source,
            access_mode=access_mode,
            status=SourceStatus.SKIPPED_DISABLED,
            detail="Source disabled in sources.yaml",
            source_cfg=source_cfg,
        )
    req = requires_env or source_cfg.requires_env
    if req and not env_value:
        return skipped_result(
            source=source,
            access_mode=access_mode,
            status=SourceStatus.SKIPPED_NOT_CONFIGURED,
            detail=f"Missing required env var {req}; source was not searched",
            source_cfg=source_cfg,
        )
    return None
