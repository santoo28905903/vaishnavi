from __future__ import annotations

import pytest

from uae_job_autopilot.config import Settings
from uae_job_autopilot.db.tables import make_session_factory
from uae_job_autopilot.models.costs import CostLedger
from uae_job_autopilot.models.routers import GenerativeRouter
from uae_job_autopilot.ops.checkpoints import CheckpointStore
from uae_job_autopilot.ops.cloud_db import DatabaseConfigError, assert_persistent_database, is_cloud_environment
from uae_job_autopilot.ops.cost_guard import CostCapExceeded, CostGuard
from uae_job_autopilot.ops.daily_pipeline import DailyPipeline
from uae_job_autopilot.ops.locks import LockNotAcquired, RunLock
from uae_job_autopilot.domain.models import ModelUsageRecord


def test_cloud_rejects_sqlite():
    settings = Settings(environment="cloud", database_url="sqlite:///./tmp.db")
    with pytest.raises(DatabaseConfigError):
        assert_persistent_database(settings)


def test_cloud_accepts_postgres_url():
    settings = Settings(
        environment="production",
        database_url="postgresql+psycopg://user:pass@db.example:5432/uae_jobs",
    )
    url = assert_persistent_database(settings)
    assert "postgres" in url


def test_lock_and_checkpoint_resume(tmp_path):
    db = tmp_path / "p4.db"
    sf = make_session_factory(f"sqlite:///{db}")
    lock = RunLock(sf, name="daily", owner="runner-1", ttl_seconds=60)
    lock.acquire()
    with pytest.raises(LockNotAcquired):
        RunLock(sf, name="daily", owner="runner-2", ttl_seconds=60).acquire()
    lock.release()
    lock2 = RunLock(sf, name="daily", owner="runner-2", ttl_seconds=60)
    lock2.acquire()
    lock2.release()

    cps = CheckpointStore(sf, "run-abc")
    cps.mark("discover", "done", payload={"selected_jobs": []})
    assert cps.is_done("discover")
    assert cps.load_payload("discover")["selected_jobs"] == []


def test_cost_guard_blocks_over_cap():
    ledger = CostLedger()
    ledger.add(
        ModelUsageRecord(
            provider="typesafe", model="jev", operation="x", cost_usd=3.0
        )
    )
    guard = CostGuard(ledger, cap_usd=2.0)
    with pytest.raises(CostCapExceeded):
        guard.check(stage="evaluate")


def test_ollama_disabled_in_cloud(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    settings = Settings(
        environment="cloud",
        ollama_enabled=True,
        enable_cloud_generative=True,
        groq_api_key="g",
    )
    # Force models config ollama on — still blocked in cloud
    from uae_job_autopilot.config import ModelsConfig

    models = ModelsConfig(ollama_enabled=True, groq_enabled=True)
    router = GenerativeRouter(settings=settings, models=models, ledger=CostLedger())
    providers = router.available_providers()
    assert "ollama" not in providers
    assert "groq" in providers
    assert is_cloud_environment(settings)


def test_daily_dry_run_local(tmp_path):
    settings = Settings(
        environment="local",
        database_url=f"sqlite:///{tmp_path / 'daily.db'}",
        enable_live_submission=False,
    )
    pipeline = DailyPipeline(settings=settings, data_dir=tmp_path)
    result = pipeline.run(dry_run=True)
    assert result.ok
    assert result.submission_enabled is False
    assert all(s.get("dry_run") for s in result.stages.values())


def test_daily_dry_run_cloud_without_db():
    settings = Settings(environment="cloud", database_url="sqlite:///./bad.db")
    pipeline = DailyPipeline(settings=settings)
    result = pipeline.run(dry_run=True)
    assert result.ok
    assert any("DB validation" in n or "dry_run" in n for n in result.notes)
