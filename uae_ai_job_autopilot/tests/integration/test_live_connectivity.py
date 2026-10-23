from __future__ import annotations

import os

import httpx
import pytest

from uae_job_autopilot.config import SearchProfile, SourceConfig
from uae_job_autopilot.discovery.adapters.ashby import AshbyAdapter
from uae_job_autopilot.discovery.adapters.greenhouse import GreenhouseAdapter
from uae_job_autopilot.discovery.adapters.jsearch import JSearchAdapter
from uae_job_autopilot.discovery.adapters.lever import LeverAdapter
from uae_job_autopilot.domain.enums import SourceStatus

PROFILE = SearchProfile(
    target_titles=["AI Engineer", "Machine Learning Engineer", "Forward Deployed Engineer", "Data Scientist"],
    title_keywords=[
        "ai",
        "ml",
        "llm",
        "machine",
        "learning",
        "engineer",
        "forward",
        "deployed",
        "scientist",
        "data",
        "generative",
        "applied",
    ],
    freshness_window_hours=24,
    evaluation_cap=50,
)

pytestmark = pytest.mark.live


def test_live_greenhouse_careem():
    adapter = GreenhouseAdapter()
    with httpx.Client(timeout=30.0) as client:
        result = adapter.fetch(
            client=client,
            profile=PROFILE,
            source_cfg=SourceConfig(enabled=True, boards=["careem"]),
        )
    assert result.health.attempted
    assert result.health.status in {SourceStatus.SUCCESS, SourceStatus.EMPTY}
    assert result.health.http_status == 200
    assert result.health.jobs_fetched_raw >= 1
    # Do not invent UAE AI jobs — EMPTY is valid if none match filters.
    for job in result.jobs:
        assert job.is_uae
        assert job.application_url.startswith("http")


def test_live_lever_palantir():
    adapter = LeverAdapter()
    with httpx.Client(timeout=30.0) as client:
        result = adapter.fetch(
            client=client,
            profile=PROFILE,
            source_cfg=SourceConfig(enabled=True, sites=["palantir"]),
        )
    assert result.health.attempted
    assert result.health.status in {SourceStatus.SUCCESS, SourceStatus.EMPTY}
    assert result.health.jobs_fetched_raw >= 1


def test_live_ashby_openai():
    adapter = AshbyAdapter()
    with httpx.Client(timeout=30.0) as client:
        result = adapter.fetch(
            client=client,
            profile=PROFILE,
            source_cfg=SourceConfig(enabled=True, boards=["openai"]),
        )
    assert result.health.attempted
    assert result.health.status in {SourceStatus.SUCCESS, SourceStatus.EMPTY}
    assert result.health.jobs_fetched_raw >= 1


def test_live_jsearch_or_skip_without_key():
    key = os.environ.get("JSEARCH_API_KEY")
    adapter = JSearchAdapter()
    with httpx.Client(timeout=30.0) as client:
        result = adapter.fetch(
            client=client,
            profile=PROFILE,
            source_cfg=SourceConfig(enabled=True, requires_env="JSEARCH_API_KEY"),
        )
    if not key:
        assert result.health.status == SourceStatus.SKIPPED_NOT_CONFIGURED
        assert result.health.attempted is False
        assert result.jobs == []
    else:
        assert result.health.attempted
        assert result.health.status in {
            SourceStatus.SUCCESS,
            SourceStatus.EMPTY,
            SourceStatus.QUOTA_EXHAUSTED,
            SourceStatus.FAILED,
        }
