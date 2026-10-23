from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from uae_job_autopilot.apply.answers import answer_field, build_screening_answers
from uae_job_autopilot.apply.channels.browser_common import page_signals
from uae_job_autopilot.apply.channels_config import load_application_channels
from uae_job_autopilot.apply.orchestrator import ApplyOrchestrator
from uae_job_autopilot.config import Settings, load_candidate_profile
from uae_job_autopilot.domain.enums import ApplicationStatus, ApplyOutcome
from uae_job_autopilot.domain.models import JobPosting
from uae_job_autopilot.reporting.gmail import build_daily_report_email


def _pdf(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Minimal PDF bytes
    path.write_bytes(
        b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    )
    return str(path)


def _job(**kwargs) -> JobPosting:
    base = dict(
        source="mock_sandbox",
        source_job_id="j1",
        title="Senior ML Engineer",
        employer="Mock Co",
        location_raw="Dubai, UAE",
        application_url="mock://apply/j1?scenario=success",
        discovered_at=datetime(2026, 10, 24, tzinfo=timezone.utc),
    )
    base.update(kwargs)
    return JobPosting.model_validate(base)


def test_channels_config_mock_enabled_real_off():
    cfg = load_application_channels()
    assert cfg.channels["mock_sandbox"].enabled is True
    assert cfg.channels["mock_sandbox"].authorized is True
    assert cfg.channels["greenhouse_browser"].enabled is False
    assert cfg.channels["greenhouse_browser"].authorized is False
    assert cfg.channels["lever_browser"].authorized is False
    assert "linkedin_jobs" in cfg.unsupported_boards


def test_truthful_screening_answers_never_claim_no_sponsorship():
    answers = build_screening_answers(load_candidate_profile())
    assert answers.requires_employer_sponsorship is True
    assert answers.authorized_to_work_without_sponsorship is False
    assert answers.willing_to_relocate_uae is True
    assert answers.notice_period_days == 30
    assert answers.expected_monthly_aed == 28000
    assert "Yes" in answers.answers_map["requires_visa_sponsorship"]
    assert answer_field(answers, "Authorized to work in the UAE without sponsorship") == "No"
    assert answer_field(answers, "Expected salary") == "28000"


def test_page_signals_detect_captcha_and_confirmation():
    assert page_signals('<div class="g-recaptcha"></div>')["captcha"] is True
    assert page_signals("Please enter your MFA authenticator code")["mfa"] is True
    assert page_signals("Thank you for applying! Application received.")["confirmation"] is True
    assert page_signals("<html>plain form</html>")["captcha"] is False


def test_mock_success_marks_applied_only_with_confirmation(tmp_path):
    settings = Settings(
        environment="local",
        database_url=f"sqlite:///{tmp_path / 'p5.db'}",
        enable_live_submission=False,
        sheets_enabled=False,
        gmail_enabled=False,
    )
    resume = _pdf(tmp_path / "resume.pdf")
    cover = _pdf(tmp_path / "cover.pdf")
    orch = ApplyOrchestrator(settings=settings, data_dir=tmp_path)
    report = orch.run(
        [
            {
                "job": _job(application_url="mock://apply/ok?scenario=success"),
                "resume_pdf": resume,
                "cover_pdf": cover,
                "ats_passed": True,
                "scenario": "success",
            }
        ],
        dry_run=False,
        sync_sheets=True,
    )
    assert report.stats.applied == 1
    assert report.attempts[0].outcome == ApplyOutcome.APPLIED
    assert report.attempts[0].confirmation_verified is True
    assert report.attempts[0].status == ApplicationStatus.APPLIED
    row = orch.repo.get_by_key(report.attempts[0].application_key)
    assert row is not None
    assert row.status == "applied"
    assert row.confirmation_verified is True
    assert row.screening_answers_json


def test_mock_captcha_never_marks_applied(tmp_path):
    settings = Settings(
        environment="local",
        database_url=f"sqlite:///{tmp_path / 'p5.db'}",
        enable_live_submission=False,
    )
    resume = _pdf(tmp_path / "r.pdf")
    cover = _pdf(tmp_path / "c.pdf")
    orch = ApplyOrchestrator(settings=settings, data_dir=tmp_path)
    report = orch.run(
        [
            {
                "job": _job(
                    source_job_id="cap",
                    application_url="mock://apply/cap?scenario=captcha",
                    employer="Captcha Co",
                ),
                "resume_pdf": resume,
                "cover_pdf": cover,
                "ats_passed": True,
                "scenario": "captcha",
            }
        ],
        dry_run=False,
        sync_sheets=False,
    )
    assert report.stats.blocked == 1
    assert report.attempts[0].outcome == ApplyOutcome.BLOCKED
    assert report.attempts[0].status == ApplicationStatus.BLOCKED
    assert "CAPTCHA" in (report.attempts[0].block_reason or "")
    assert report.attempts[0].confirmation_verified is False


def test_mock_unverified_not_applied(tmp_path):
    settings = Settings(
        environment="local",
        database_url=f"sqlite:///{tmp_path / 'p5.db'}",
        enable_live_submission=False,
    )
    resume = _pdf(tmp_path / "r.pdf")
    cover = _pdf(tmp_path / "c.pdf")
    orch = ApplyOrchestrator(settings=settings, data_dir=tmp_path)
    report = orch.run(
        [
            {
                "job": _job(
                    source_job_id="uv",
                    application_url="https://mock.uae-job-autopilot.local/x?scenario=unverified",
                    employer="Unverified Co",
                ),
                "resume_pdf": resume,
                "cover_pdf": cover,
                "ats_passed": True,
                "scenario": "unverified",
            }
        ],
        dry_run=False,
        sync_sheets=False,
    )
    assert report.stats.submission_unverified == 1
    assert report.attempts[0].status == ApplicationStatus.SUBMISSION_UNVERIFIED
    assert report.attempts[0].confirmation_verified is False


def test_unsupported_board_honest_skip(tmp_path):
    settings = Settings(
        environment="local",
        database_url=f"sqlite:///{tmp_path / 'p5.db'}",
        enable_live_submission=True,  # even with live on, LinkedIn is unsupported
    )
    resume = _pdf(tmp_path / "r.pdf")
    cover = _pdf(tmp_path / "c.pdf")
    orch = ApplyOrchestrator(settings=settings, data_dir=tmp_path)
    report = orch.run(
        [
            {
                "job": _job(
                    source="linkedin_jobs",
                    source_job_id="li1",
                    application_url="https://www.linkedin.com/jobs/view/99",
                    employer="LI Co",
                ),
                "resume_pdf": resume,
                "cover_pdf": cover,
                "ats_passed": True,
            }
        ],
        dry_run=False,
        sync_sheets=False,
    )
    assert report.stats.skipped_unsupported == 1
    assert report.attempts[0].outcome == ApplyOutcome.SKIPPED_UNSUPPORTED
    assert report.attempts[0].status != ApplicationStatus.APPLIED


def test_greenhouse_without_auth_does_not_apply(tmp_path):
    settings = Settings(
        environment="local",
        database_url=f"sqlite:///{tmp_path / 'p5.db'}",
        enable_live_submission=True,
    )
    resume = _pdf(tmp_path / "r.pdf")
    cover = _pdf(tmp_path / "c.pdf")
    orch = ApplyOrchestrator(settings=settings, data_dir=tmp_path)
    report = orch.run(
        [
            {
                "job": _job(
                    source="greenhouse",
                    source_job_id="gh1",
                    application_url="https://boards.greenhouse.io/example/jobs/123",
                    employer="GH Co",
                ),
                "resume_pdf": resume,
                "cover_pdf": cover,
                "ats_passed": True,
            }
        ],
        dry_run=False,
        sync_sheets=False,
    )
    # Channel exists in allowlist but enabled=false authorized=false
    assert report.attempts[0].status != ApplicationStatus.APPLIED
    assert report.attempts[0].outcome in {
        ApplyOutcome.SKIPPED_UNSUPPORTED,
        ApplyOutcome.CHECKLIST_FAILED,
        ApplyOutcome.DRY_RUN,
        ApplyOutcome.BLOCKED,
    }


def test_duplicate_protection(tmp_path):
    settings = Settings(
        environment="local",
        database_url=f"sqlite:///{tmp_path / 'p5.db'}",
        enable_live_submission=False,
    )
    resume = _pdf(tmp_path / "r.pdf")
    cover = _pdf(tmp_path / "c.pdf")
    orch = ApplyOrchestrator(settings=settings, data_dir=tmp_path)
    cand = {
        "job": _job(application_url="mock://apply/dup?scenario=success"),
        "resume_pdf": resume,
        "cover_pdf": cover,
        "ats_passed": True,
        "scenario": "success",
    }
    first = orch.run([cand], dry_run=False, sync_sheets=False)
    assert first.stats.applied == 1
    second = orch.run([cand], dry_run=False, sync_sheets=False)
    assert second.stats.duplicates == 1
    assert second.attempts[0].outcome == ApplyOutcome.DUPLICATE


def test_dry_run_never_applied(tmp_path):
    settings = Settings(
        environment="local",
        database_url=f"sqlite:///{tmp_path / 'p5.db'}",
        enable_live_submission=False,
    )
    resume = _pdf(tmp_path / "r.pdf")
    cover = _pdf(tmp_path / "c.pdf")
    orch = ApplyOrchestrator(settings=settings, data_dir=tmp_path)
    report = orch.run(
        [
            {
                "job": _job(),
                "resume_pdf": resume,
                "cover_pdf": cover,
                "ats_passed": True,
                "scenario": "success",
            }
        ],
        dry_run=True,
        sync_sheets=False,
    )
    assert report.stats.dry_run == 1
    assert report.stats.applied == 0
    assert report.attempts[0].status == ApplicationStatus.DRY_RUN


def test_continue_after_block(tmp_path):
    settings = Settings(
        environment="local",
        database_url=f"sqlite:///{tmp_path / 'p5.db'}",
        enable_live_submission=False,
    )
    resume = _pdf(tmp_path / "r.pdf")
    cover = _pdf(tmp_path / "c.pdf")
    orch = ApplyOrchestrator(settings=settings, data_dir=tmp_path)
    report = orch.run(
        [
            {
                "job": _job(
                    source_job_id="a",
                    application_url="mock://apply/a?scenario=captcha",
                    employer="A",
                ),
                "resume_pdf": resume,
                "cover_pdf": cover,
                "ats_passed": True,
                "scenario": "captcha",
            },
            {
                "job": _job(
                    source_job_id="b",
                    application_url="mock://apply/b?scenario=success",
                    employer="B",
                ),
                "resume_pdf": resume,
                "cover_pdf": cover,
                "ats_passed": True,
                "scenario": "success",
            },
        ],
        dry_run=False,
        sync_sheets=False,
    )
    assert report.stats.blocked == 1
    assert report.stats.applied == 1
    assert len(report.attempts) == 2


def test_email_includes_apply_outcomes():
    subject, body = build_daily_report_email(
        discovery_stats={"jobs_selected_for_evaluation": 2},
        evaluation_stats={"match_pass": 2},
        document_stats={"documents_generated": 2},
        sources_queried=["greenhouse"],
        sources_unavailable=[],
        top_links=["https://example.com/job"],
        model_cost_usd=0.01,
        failures=[],
        apply_stats={
            "applied": 1,
            "submission_unverified": 1,
            "blocked": 1,
            "dry_run": 0,
            "skipped_unsupported": 1,
            "duplicates": 0,
            "checklist_failed": 0,
            "errors": 0,
        },
        live_submission_enabled=False,
    )
    assert "Applications confirmed (applied): 1" in body
    assert "submission_unverified: 1" in body
    assert "blocked" in body
    assert "Phase 5 not enabled" not in body


def test_fixture_batch_file(tmp_path):
    settings = Settings(
        environment="local",
        database_url=f"sqlite:///{tmp_path / 'p5.db'}",
        enable_live_submission=False,
    )
    resume = _pdf(tmp_path / "r.pdf")
    cover = _pdf(tmp_path / "c.pdf")
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "apply" / "mock_candidates.json"
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    candidates = []
    for c in raw["candidates"]:
        c = dict(c)
        c["resume_pdf"] = resume
        c["cover_pdf"] = cover
        candidates.append(c)
    orch = ApplyOrchestrator(settings=settings, data_dir=tmp_path)
    report = orch.run(candidates, dry_run=False, sync_sheets=False)
    assert report.stats.applied == 1
    assert report.stats.blocked == 1
    assert report.stats.submission_unverified == 1
    assert report.stats.skipped_unsupported == 1
    # Never mark blocked/unverified/unsupported as applied
    for a in report.attempts:
        if a.outcome != ApplyOutcome.APPLIED:
            assert a.status != ApplicationStatus.APPLIED
            assert a.confirmation_verified is False
