from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from uae_job_autopilot.config import Settings, load_models_config
from uae_job_autopilot.domain.enums import MatchDecision
from uae_job_autopilot.domain.models import JobPosting
from uae_job_autopilot.matching.pipeline import MatchingPipeline
from uae_job_autopilot.matching.resume import load_parsed_resume
from uae_job_autopilot.models.costs import CostLedger
from uae_job_autopilot.models.embeddings import EmbeddingService
from uae_job_autopilot.models.jev import JevClient, score_answer_to_100

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "jobs" / "representative_jobs.json"


def _jobs() -> list[JobPosting]:
    data = json.loads(FIXTURES.read_text())
    return [JobPosting.model_validate(j) for j in data["jobs"]]


class FakeEmbeddings(EmbeddingService):
    def __init__(self) -> None:
        super().__init__(models=load_models_config(), ledger=CostLedger(), model=object())

    def similarity_0_100(self, text_a: str, text_b: str) -> float:  # noqa: ARG002
        # High semantic fit for GenAI/RAG titles; mid otherwise
        blob = (text_b or "").lower()
        if "generative ai" in blob or "rag" in blob or "llm" in blob:
            return 82.0
        if "machine learning" in blob or "data scientist" in blob:
            return 70.0
        return 55.0


def _mock_jev_response(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode())
    state = payload.get("state") or {}
    job = state.get("job") if isinstance(state, dict) else {}
    title = str((job or {}).get("title") or "").lower()
    desc = str((job or {}).get("description") or "").lower()
    blob = title + " " + desc

    if "emirati" in blob or "nationals only" in blob:
        visa = "nationals_only"
    elif "sponsorship is not available" in blob or "already have a valid uae" in blob:
        visa = "no_sponsorship"
    elif "visa sponsorship available" in blob:
        visa = "sponsors"
    else:
        visa = "unclear"

    strong = "generative" in blob or "rag" in blob or "llm" in blob
    return httpx.Response(
        200,
        json={
            "model": "jev-1.14.0",
            "answers": {
                "job_relevance": {
                    "type": "score",
                    "score": 2.0 if strong else 1.0,
                    "confidence": 0.7,
                    "probabilities": {"0": 0.05, "1": 0.15, "2": 0.8},
                },
                "skill_alignment": {
                    "type": "score",
                    "score": 1.8 if strong else 1.0,
                    "confidence": 0.65,
                    "probabilities": {"0": 0.1, "1": 0.2, "2": 0.7},
                },
                "seniority_ok": {"type": "noul", "noul": 0.85 if "12 years" not in blob else 0.1},
                "visa_evidence": {
                    "type": "choice",
                    "choice": visa,
                    "confidence": 0.75,
                    "probabilities": {visa: 0.75},
                },
                "next_action": {
                    "type": "choice",
                    "choice": "advance" if strong and visa == "sponsors" else "reject",
                    "confidence": 0.6,
                    "probabilities": {"advance": 0.6, "reject": 0.3, "hold_review": 0.1},
                },
            },
            "usage": {"input_tokens": 500, "output_tokens": 0},
        },
    )


def test_score_answer_calibration():
    assert score_answer_to_100({"type": "score", "score": 0}) == 0
    assert score_answer_to_100({"type": "score", "score": 2}) == 100
    assert score_answer_to_100({"type": "score", "score": 1}) == 50


def test_resume_parse_does_not_invent_employer():
    profile = load_parsed_resume()
    assert profile.full_name.startswith("Vaishnavi")
    assert "Python" in profile.skills or profile.resume_text
    # Must not invent employers beyond resume/config
    assert "Google" in profile.current_employer or "Relanto" in profile.current_employer


def test_pipeline_blocks_and_passes_with_mocked_jev(tmp_path):
    transport = httpx.MockTransport(_mock_jev_response)
    client = httpx.Client(transport=transport)
    settings = Settings(typesafe_api_key="test-key", jev_model="jev-1.14.0")
    ledger = CostLedger()
    from uae_job_autopilot.models.cache import JsonFileCache

    jev = JevClient(
        settings=settings,
        models=load_models_config(),
        ledger=ledger,
        cache=JsonFileCache("jev_test", root=tmp_path / "cache"),
        client=client,
    )
    pipeline = MatchingPipeline(
        settings=settings,
        models=load_models_config(),
        profile=load_parsed_resume(),
        jev=jev,
        embeddings=FakeEmbeddings(),
        ledger=ledger,
        data_dir=tmp_path,
    )
    report = pipeline.evaluate_jobs(_jobs())
    by_id = {r.job.source_job_id: r for r in report.results}

    assert by_id["nationals-only-1"].decision == MatchDecision.BLOCKED
    assert by_id["no-sponsor-1"].decision == MatchDecision.BLOCKED
    assert by_id["low-salary-1"].decision == MatchDecision.BLOCKED
    assert by_id["exp-gap-1"].decision == MatchDecision.BLOCKED

    good = by_id["good-rag-1"]
    assert good.decision == MatchDecision.PASS
    assert good.resume_fit and good.resume_fit.combined_score >= 75
    assert good.visa and good.visa.passed
    assert good.visa.sponsorship_confirmed is True

    unclear = by_id["unclear-visa-1"]
    assert unclear.visa is not None
    assert unclear.visa.sponsorship_confirmed is False

    assert report.stats.hard_blocked >= 4
    assert report.stats.total_input_tokens > 0
    assert any(u.cost_usd > 0 or u.cached for u in report.usage if u.provider == "typesafe")
