import json
from pathlib import Path

from uae_job_autopilot.config import load_candidate_profile, load_models_config
from uae_job_autopilot.domain.enums import SponsorshipLabel
from uae_job_autopilot.domain.models import JobPosting
from uae_job_autopilot.matching.hard_rules import evaluate_hard_exclusions
from uae_job_autopilot.matching.visa import combine_visa_assessment, deterministic_visa_signals

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "jobs" / "representative_jobs.json"


def _jobs() -> list[JobPosting]:
    data = json.loads(FIXTURES.read_text())
    return [JobPosting.model_validate(j) for j in data["jobs"]]


def test_hard_block_nationals_only_and_no_sponsor_and_salary():
    profile = load_candidate_profile()
    by_id = {j.source_job_id: j for j in _jobs()}

    nat = evaluate_hard_exclusions(by_id["nationals-only-1"], profile)
    assert any(x.code == "emirati_nationals_only" for x in nat)

    nos = evaluate_hard_exclusions(by_id["no-sponsor-1"], profile)
    assert any(x.code == "no_visa_sponsorship" for x in nos)

    low = evaluate_hard_exclusions(by_id["low-salary-1"], profile)
    assert any(x.code == "salary_below_floor" for x in low)

    exp = evaluate_hard_exclusions(by_id["exp-gap-1"], profile)
    assert any(x.code == "experience_gap" for x in exp)

    good = evaluate_hard_exclusions(by_id["good-rag-1"], profile)
    assert good == []


def test_visa_unknown_not_confirmed():
    profile = load_candidate_profile()
    models = load_models_config()
    by_id = {j.source_job_id: j for j in _jobs()}
    job = by_id["unclear-visa-1"]
    score, label, signals, _ = deterministic_visa_signals(job)
    assert label == SponsorshipLabel.UNCLEAR
    assert "sponsorship_not_stated" in signals

    assessment = combine_visa_assessment(job, profile, models, jev_answer=None)
    assert assessment.sponsorship_confirmed is False
    assert "unknown/unclear" in " ".join(assessment.notes).lower() or not assessment.sponsorship_confirmed


def test_explicit_sponsors_confirmed_when_language_present():
    profile = load_candidate_profile()
    models = load_models_config()
    job = next(j for j in _jobs() if j.source_job_id == "good-rag-1")
    assessment = combine_visa_assessment(
        job,
        profile,
        models,
        jev_answer={"type": "choice", "choice": "sponsors", "confidence": 0.8},
    )
    assert assessment.sponsorship_label == SponsorshipLabel.SPONSORS
    assert assessment.sponsorship_confirmed is True
    assert assessment.combined_score >= models.visa_threshold
