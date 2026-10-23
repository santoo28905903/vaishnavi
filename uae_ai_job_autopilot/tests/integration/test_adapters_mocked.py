from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from uae_job_autopilot.config import SearchProfile, SourceConfig
from uae_job_autopilot.discovery.adapters.ashby import AshbyAdapter
from uae_job_autopilot.discovery.adapters.greenhouse import GreenhouseAdapter
from uae_job_autopilot.discovery.adapters.jsearch import JSearchAdapter
from uae_job_autopilot.discovery.adapters.lever import LeverAdapter
from uae_job_autopilot.discovery.adapters.alerts import linkedin_adapter
from uae_job_autopilot.domain.enums import SourceStatus

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PROFILE = SearchProfile(
    target_titles=["AI Engineer", "Machine Learning Engineer", "Forward Deployed Engineer"],
    title_keywords=[
        "ai",
        "ml",
        "machine",
        "learning",
        "engineer",
        "forward",
        "deployed",
        "generative",
        "scientist",
        "data",
    ],
    freshness_window_hours=24,
    evaluation_cap=50,
)


@respx.mock
def test_greenhouse_filters_uae_and_title():
    payload = json.loads((FIXTURES / "greenhouse/careem_jobs.json").read_text())
    respx.get("https://boards-api.greenhouse.io/v1/boards/careem/jobs").mock(
        return_value=httpx.Response(200, json=payload)
    )
    adapter = GreenhouseAdapter()
    with httpx.Client() as client:
        result = adapter.fetch(
            client=client,
            profile=PROFILE,
            source_cfg=SourceConfig(enabled=True, boards=["careem"]),
        )
    assert result.health.attempted is True
    assert result.health.status == SourceStatus.SUCCESS
    assert result.health.jobs_fetched_raw == 3
    assert len(result.jobs) == 1
    assert result.jobs[0].title == "Senior Machine Learning Engineer"
    assert result.jobs[0].is_uae


@respx.mock
def test_lever_maps_uae_forward_deployed():
    payload = json.loads((FIXTURES / "lever/palantir.json").read_text())
    respx.get(url__regex=r"https://api\.lever\.co/v0/postings/palantir.*").mock(
        return_value=httpx.Response(200, json=payload)
    )
    adapter = LeverAdapter()
    with httpx.Client() as client:
        result = adapter.fetch(
            client=client,
            profile=PROFILE,
            source_cfg=SourceConfig(enabled=True, sites=["palantir"]),
        )
    assert result.health.attempted
    assert len(result.jobs) == 1
    assert "Forward Deployed" in result.jobs[0].title


@respx.mock
def test_ashby_maps_uae_role():
    payload = json.loads((FIXTURES / "ashby/openai_jobs.json").read_text())
    respx.get("https://api.ashbyhq.com/posting-api/job-board/openai").mock(
        return_value=httpx.Response(200, json=payload)
    )
    adapter = AshbyAdapter()
    with httpx.Client() as client:
        result = adapter.fetch(
            client=client,
            profile=PROFILE,
            source_cfg=SourceConfig(enabled=True, boards=["openai"]),
        )
    assert len(result.jobs) == 1
    assert result.jobs[0].location_raw.startswith("Abu Dhabi")


@respx.mock
def test_jsearch_skipped_without_api_key(monkeypatch):
    monkeypatch.delenv("JSEARCH_API_KEY", raising=False)
    # Ensure settings re-read — Settings() reads env at init
    from uae_job_autopilot import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: cfg.Settings(jsearch_api_key=None))
    adapter = JSearchAdapter()
    with httpx.Client() as client:
        result = adapter.fetch(
            client=client,
            profile=PROFILE,
            source_cfg=SourceConfig(enabled=True, requires_env="JSEARCH_API_KEY"),
        )
    assert result.health.attempted is False
    assert result.health.status == SourceStatus.SKIPPED_NOT_CONFIGURED
    assert result.jobs == []


@respx.mock
def test_jsearch_with_key(monkeypatch):
    monkeypatch.setenv("JSEARCH_API_KEY", "test-key")
    from uae_job_autopilot import config as cfg

    monkeypatch.setattr(
        cfg, "get_settings", lambda: cfg.Settings(jsearch_api_key="test-key")
    )
    payload = json.loads((FIXTURES / "jsearch/sample.json").read_text())
    respx.get(url__startswith="https://jsearch.p.rapidapi.com/search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    adapter = JSearchAdapter()
    with httpx.Client() as client:
        result = adapter.fetch(
            client=client,
            profile=PROFILE,
            source_cfg=SourceConfig(enabled=True, requires_env="JSEARCH_API_KEY"),
        )
    assert result.health.attempted
    assert result.health.status == SourceStatus.SUCCESS
    assert len(result.jobs) >= 1
    assert result.jobs[0].source == "jsearch"


def test_linkedin_alert_ingestion(tmp_path):
    alert_dir = tmp_path / "linkedin_jobs"
    alert_dir.mkdir()
    sample = (FIXTURES / "alerts/sample_linkedin.json").read_text()
    (alert_dir / "export.json").write_text(sample, encoding="utf-8")
    adapter = linkedin_adapter()
    with httpx.Client() as client:
        result = adapter.fetch(
            client=client,
            profile=PROFILE,
            source_cfg=SourceConfig(
                enabled=True,
                status="alert_ingestion",
                alert_dir=str(alert_dir),
            ),
        )
    assert result.health.attempted
    assert len(result.jobs) == 1
    assert result.jobs[0].source == "linkedin_jobs"


def test_linkedin_missing_alerts_not_searched(tmp_path):
    adapter = linkedin_adapter()
    missing = tmp_path / "does-not-exist"
    with httpx.Client() as client:
        result = adapter.fetch(
            client=client,
            profile=PROFILE,
            source_cfg=SourceConfig(
                enabled=True,
                status="alert_ingestion",
                alert_dir=str(missing),
            ),
        )
    assert result.health.attempted is False
    assert result.health.status == SourceStatus.SKIPPED_NOT_CONFIGURED
    assert "not searched" in (result.health.detail or "").lower()
