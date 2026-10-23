from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from uae_job_autopilot.config import Settings, load_models_config
from uae_job_autopilot.domain.models import JobPosting
from uae_job_autopilot.matching.resume import candidate_state_for_jev, load_parsed_resume
from uae_job_autopilot.models.jev import JevClient

pytestmark = pytest.mark.live

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "jobs" / "representative_jobs.json"


@pytest.mark.skipif(
    not os.environ.get("TYPESAFE_API_KEY"),
    reason="TYPESAFE_API_KEY not set — skipping live Jev call",
)
def test_live_jev_system_one_smoke():
    data = json.loads(FIXTURES.read_text())
    job = JobPosting.model_validate(
        next(j for j in data["jobs"] if j["source_job_id"] == "good-rag-1")
    )
    profile = load_parsed_resume()
    settings = Settings(
        typesafe_api_key=os.environ["TYPESAFE_API_KEY"],
        jev_model=os.environ.get("JEV_MODEL", "jev-1.14.0"),
    )
    with JevClient(settings=settings, models=load_models_config()) as client:
        result = client.job_decision_bundle(
            job_state={
                "title": job.title,
                "employer": job.employer,
                "location": job.location_raw,
                "description": job.description_text,
            },
            candidate_state=candidate_state_for_jev(profile),
        )
    assert "answers" in result
    answers = result["answers"]
    for key in (
        "job_relevance",
        "skill_alignment",
        "seniority_ok",
        "visa_evidence",
        "next_action",
    ):
        assert key in answers
    assert client.ledger.total_input_tokens > 0
