from __future__ import annotations

import json
from pathlib import Path

from uae_job_autopilot.config import Settings
from uae_job_autopilot.db.repository import ApplicationRepository
from uae_job_autopilot.documents.master import build_master_resume
from uae_job_autopilot.documents.pipeline import Phase3Pipeline
from uae_job_autopilot.domain.enums import MatchDecision
from uae_job_autopilot.domain.models import JobMatchResult, JobPosting
from uae_job_autopilot.reporting.gmail import (
    InMemoryEmailClient,
    build_daily_report_email,
    send_daily_report_with_recovery,
)
from uae_job_autopilot.tracking.sheets import (
    InMemorySheetsClient,
    SHEET_TABS,
    sync_phase3_workbook,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "jobs" / "representative_jobs.json"


def _job(job_id: str = "good-rag-1") -> JobPosting:
    data = json.loads(FIXTURES.read_text())
    return JobPosting.model_validate(next(j for j in data["jobs"] if j["source_job_id"] == job_id))


def test_db_idempotent_upsert(tmp_path):
    db = tmp_path / "t.db"
    repo = ApplicationRepository.from_url(f"sqlite:///{db}")
    payload = {
        "application_key": "abc123",
        "employer": "Core42",
        "title": "AI Engineer",
        "location": "Abu Dhabi",
        "application_url": "https://example.com/1",
        "source": "fixture",
        "source_job_id": "1",
        "status": "prepared",
        "decision": "pass",
        "ats_passed": True,
        "sponsorship_label": "sponsors",
        "sponsorship_confirmed": True,
    }
    a = repo.upsert_application(payload)
    payload["ats_score"] = 88.0
    b = repo.upsert_application(payload)
    assert a.id == b.id
    assert b.ats_score == 88.0
    assert len(repo.list_applications()) == 1


def test_sheets_upsert_and_error_recovery():
    client = InMemorySheetsClient()
    sync_phase3_workbook(
        client,
        dashboard={"run_id": "r1"},
        applications=[{"application_key": "k1", "title": "A"}],
        today_jobs=[{"application_key": "k1"}],
        rejected=[],
        run_history=[{"run_id": "r1"}],
        source_health=[{"source": "greenhouse", "status": "success"}],
        model_costs=[{"id": "1", "cost_usd": 0}],
    )
    assert set(client.tabs) >= set(SHEET_TABS)
    assert client.read_tab("Applications")[0]["application_key"] == "k1"

    # Idempotent second upsert
    client.upsert_rows(
        "Applications",
        [{"application_key": "k1", "title": "A2"}],
        key_field="application_key",
    )
    assert len(client.read_tab("Applications")) == 1
    assert client.read_tab("Applications")[0]["title"] == "A2"

    # Recovery: one tab fails, others continue
    client.fail_next_replace = True
    result = sync_phase3_workbook(
        client,
        dashboard={"run_id": "r2"},
        applications=[{"application_key": "k2", "title": "B"}],
        today_jobs=[],
        rejected=[],
        run_history=[{"run_id": "r2"}],
        source_health=[],
        model_costs=[],
    )
    assert result["ok"] is False
    assert "Dashboard" in result["errors"]
    assert any(r["application_key"] == "k2" for r in client.read_tab("Applications"))


def test_email_zero_jobs_vs_unavailable_and_recovery():
    subj1, body1 = build_daily_report_email(
        discovery_stats={"jobs_selected_for_evaluation": 0},
        evaluation_stats=None,
        document_stats={"documents_generated": 0},
        sources_queried=["greenhouse"],
        sources_unavailable=[],
        top_links=[],
        model_cost_usd=0,
        failures=[],
        zero_jobs=True,
        discovery_unavailable=False,
    )
    assert "zero" in subj1.lower()
    assert "zero verified-fresh" in body1.lower()

    subj2, body2 = build_daily_report_email(
        discovery_stats=None,
        evaluation_stats=None,
        document_stats=None,
        sources_queried=[],
        sources_unavailable=[{"source": "jsearch", "status": "skipped_not_configured", "detail": "no key"}],
        top_links=[],
        model_cost_usd=0,
        failures=["jsearch missing key"],
        discovery_unavailable=True,
    )
    assert "unavailable" in subj2.lower()
    assert "unavailable" in body2.lower()

    mail = InMemoryEmailClient()
    mail.fail_next = True
    result = send_daily_report_with_recovery(
        mail, to="vaishnavibatchu28@gmail.com", subject=subj1, body=body1
    )
    assert result["status"] == "failed"
    # retry path success
    result2 = send_daily_report_with_recovery(
        mail, to="vaishnavibatchu28@gmail.com", subject=subj1, body=body1
    )
    assert result2["status"] == "sent"
    assert mail.sent


def test_phase3_pipeline_end_to_end(tmp_path):
    build_master_resume(persist=True)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'p3.db'}")
    sheets = InMemorySheetsClient()
    mail = InMemoryEmailClient()
    pipeline = Phase3Pipeline(
        settings=settings,
        sheets=sheets,
        email=mail,
        data_dir=tmp_path,
    )
    job = _job()
    match = JobMatchResult(job=job, decision=MatchDecision.PASS, next_action="advance")
    blocked = JobMatchResult(
        job=_job("nationals-only-1"),
        decision=MatchDecision.BLOCKED,
        next_action="reject",
    )
    report = pipeline.prepare_documents_for_matches(
        [match, blocked],
        send_email=True,
        sync_sheets=True,
        sources_queried=["greenhouse"],
        sources_unavailable=[],
    )
    assert report.stats["documents_generated"] == 1
    assert report.stats["ats_pass"] >= 1
    assert report.stats["db_upserts"] == 2
    assert report.email_result.get("status") == "sent"
    assert sheets.read_tab("Applications")
    assert Path(report.documents[0].resume_pdf).exists()
