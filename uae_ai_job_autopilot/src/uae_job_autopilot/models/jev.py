from __future__ import annotations

import logging
from typing import Any

import httpx

from uae_job_autopilot.config import ModelsConfig, Settings, get_settings, load_models_config
from uae_job_autopilot.domain.models import ModelUsageRecord
from uae_job_autopilot.models.cache import JsonFileCache
from uae_job_autopilot.models.costs import CostLedger

logger = logging.getLogger(__name__)


class JevNotConfiguredError(RuntimeError):
    """Raised when TYPESAFE_API_KEY is missing and a live Jev call is required."""


class JevClient:
    """TypeSafe System One client for structured Jev decisions (not prose)."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        models: ModelsConfig | None = None,
        ledger: CostLedger | None = None,
        cache: JsonFileCache | None = None,
        client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.models = models or load_models_config()
        self.ledger = ledger or CostLedger()
        self.cache = cache or JsonFileCache("jev_decisions")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(60.0, connect=15.0),
            transport=transport,
        )

    @property
    def configured(self) -> bool:
        return bool(self.settings.typesafe_api_key)

    @property
    def model_name(self) -> str:
        return self.settings.jev_model or self.models.jev_default_model

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> JevClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def evaluate(
        self,
        *,
        state: str | dict[str, Any],
        questions: dict[str, dict[str, Any]],
        operation: str,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        POST /v1/systemone — returns raw response dict with answers + usage.
        Never invents answers when the API is unavailable.
        """
        if not self.configured:
            raise JevNotConfiguredError(
                "TYPESAFE_API_KEY is not set; Jev was not called"
            )

        cache_key = JsonFileCache.key_for(self.model_name, operation, state, questions)
        if use_cache:
            cached = self.cache.get_json(cache_key)
            if cached is not None:
                self.ledger.add(
                    ModelUsageRecord(
                        provider="typesafe",
                        model=str(cached.get("model") or self.model_name),
                        operation=operation,
                        input_tokens=int((cached.get("usage") or {}).get("input_tokens") or 0),
                        output_tokens=int((cached.get("usage") or {}).get("output_tokens") or 0),
                        cost_usd=0.0,
                        cached=True,
                        meta={"cache_key": cache_key},
                    )
                )
                return cached

        payload = {
            "model": self.model_name,
            "state": state,
            "questions": questions,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.typesafe_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = self.models.jev_endpoint
        try:
            response = self._client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            self.ledger.add(
                ModelUsageRecord(
                    provider="typesafe",
                    model=self.model_name,
                    operation=operation,
                    error=str(exc),
                )
            )
            raise

        if response.status_code >= 400:
            err = f"HTTP {response.status_code}: {response.text[:400]}"
            self.ledger.add(
                ModelUsageRecord(
                    provider="typesafe",
                    model=self.model_name,
                    operation=operation,
                    error=err,
                    meta={"http_status": response.status_code},
                )
            )
            response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected Jev response type")

        usage = data.get("usage") or {}
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        cost = self.ledger.estimate_jev_cost(
            input_tokens=input_tokens,
            cost_per_mtok_input_usd=self.models.jev_cost_per_mtok_input_usd,
        )
        self.ledger.add(
            ModelUsageRecord(
                provider="typesafe",
                model=str(data.get("model") or self.model_name),
                operation=operation,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                cached=False,
            )
        )
        if use_cache:
            self.cache.set_json(cache_key, data)
        return data

    def job_decision_bundle(
        self,
        *,
        job_state: dict[str, Any],
        candidate_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Typed questions for relevance, skills, seniority, visa, next action."""
        state = {
            "candidate": candidate_state,
            "job": job_state,
            "instructions": (
                "Evaluate only from provided evidence. Do not invent qualifications. "
                "Unknown visa sponsorship is not confirmed sponsorship."
            ),
        }
        questions = {
            "job_relevance": {
                "type": "score",
                "instructions": (
                    "How relevant is this UAE AI/ML job to a Senior Data Scientist / "
                    "Generative AI engineer with ~4 years experience in RAG, LangGraph, "
                    "Vertex AI, and production GenAI?"
                ),
                "criteria": [
                    "Irrelevant or wrong domain",
                    "Partially related",
                    "Strongly relevant AI/ML role",
                ],
            },
            "skill_alignment": {
                "type": "score",
                "instructions": (
                    "How well do the candidate's stated skills align with mandatory "
                    "technical requirements in the job? Penalize missing hard requirements."
                ),
                "criteria": [
                    "Major mandatory skill gaps",
                    "Partial alignment",
                    "Strong mandatory skill coverage",
                ],
            },
            "seniority_ok": {
                "type": "noul",
                "instructions": (
                    "Is the candidate's ~4 years experience compatible with the role's "
                    "stated seniority/experience requirements? Answer yes if compatible "
                    "or if experience requirements are unspecified."
                ),
            },
            "visa_evidence": {
                "type": "choice",
                "instructions": (
                    "Classify employer visa sponsorship evidence in the job text. "
                    "Use nationals_only for Emirati/UAE-national-only roles. "
                    "Use unclear when sponsorship is not stated."
                ),
                "criteria": {
                    "sponsors": "Explicit employer-sponsored UAE work authorization / visa sponsorship",
                    "no_sponsorship": "Explicitly states no visa sponsorship or candidates must already have UAE status",
                    "nationals_only": "Restricted to UAE nationals / Emirati only",
                    "unclear": "Sponsorship not stated or ambiguous",
                },
            },
            "next_action": {
                "type": "choice",
                "instructions": "Recommended next pipeline action for this job given the evidence.",
                "criteria": {
                    "advance": "Advance to document generation / application prep",
                    "reject": "Reject — poor fit or explicit blocker",
                    "hold_review": "Hold for human review due to uncertainty",
                },
            },
        }
        return self.evaluate(
            state=state,
            questions=questions,
            operation="job_decision_bundle",
        )


def score_answer_to_100(answer: dict[str, Any] | None, *, levels: int = 3) -> float | None:
    """Map Jev score primitive (0..levels-1) to 0..100."""
    if not answer or answer.get("type") != "score":
        return None
    raw = answer.get("score")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    denom = max(levels - 1, 1)
    return max(0.0, min(100.0, (value / denom) * 100.0))


def noul_to_100(answer: dict[str, Any] | None) -> float | None:
    if not answer or answer.get("type") != "noul":
        return None
    try:
        return max(0.0, min(100.0, float(answer.get("noul")) * 100.0))
    except (TypeError, ValueError):
        return None
