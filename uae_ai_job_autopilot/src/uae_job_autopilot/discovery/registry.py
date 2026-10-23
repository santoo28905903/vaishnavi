from __future__ import annotations

from uae_job_autopilot.config import SourceConfig, SourcesConfig
from uae_job_autopilot.discovery.adapters import (
    AshbyAdapter,
    GreenhouseAdapter,
    JSearchAdapter,
    LeverAdapter,
    bayt_adapter,
    gulftalent_adapter,
    indeed_uae_adapter,
    linkedin_adapter,
    michael_page_adapter,
    naukrigulf_adapter,
)
from uae_job_autopilot.discovery.base import SourceAdapter


def build_adapter_registry() -> dict[str, SourceAdapter]:
    return {
        "greenhouse": GreenhouseAdapter(),
        "lever": LeverAdapter(),
        "ashby": AshbyAdapter(),
        "jsearch": JSearchAdapter(),
        "linkedin_jobs": linkedin_adapter(),
        "naukrigulf": naukrigulf_adapter(),
        "indeed_uae": indeed_uae_adapter(),
        "bayt": bayt_adapter(),
        "gulftalent": gulftalent_adapter(),
        "michael_page": michael_page_adapter(),
    }


def iter_configured_sources(
    sources: SourcesConfig,
) -> list[tuple[str, SourceConfig, str]]:
    """Return (name, config, category) in deterministic order."""
    ordered: list[tuple[str, SourceConfig, str]] = []
    for name, cfg in sources.ats_public.items():
        ordered.append((name, cfg, "ats_public"))
    for name, cfg in sources.aggregators.items():
        ordered.append((name, cfg, "aggregators"))
    for name, cfg in sources.job_boards.items():
        ordered.append((name, cfg, "job_boards"))
    for name, cfg in sources.recruiters.items():
        ordered.append((name, cfg, "recruiters"))
    return ordered
