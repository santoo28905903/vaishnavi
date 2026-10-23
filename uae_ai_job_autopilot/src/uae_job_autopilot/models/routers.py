from __future__ import annotations

import logging
from typing import Any

import httpx

from uae_job_autopilot.config import ModelsConfig, Settings, get_settings, load_models_config
from uae_job_autopilot.domain.models import ModelUsageRecord
from uae_job_autopilot.models.costs import CostLedger

logger = logging.getLogger(__name__)


class GenerativeRouter:
    """
    Optional prose helpers. Decision authority remains Jev + deterministic rules.

    Local Ollama is disabled in cloud by default (must not depend on user's Mac).
    Groq / Gemini are opt-in via config + env keys.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        models: ModelsConfig | None = None,
        ledger: CostLedger | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.models = models or load_models_config()
        self.ledger = ledger or CostLedger()
        self._owns = client is None
        self._client = client or httpx.Client(timeout=60.0)

    def close(self) -> None:
        if self._owns:
            self._client.close()

    def available_providers(self) -> list[str]:
        out: list[str] = []
        if self.models.ollama_enabled and self.settings.ollama_enabled:
            out.append("ollama")
        if self.models.groq_enabled and self.settings.groq_api_key and self.settings.enable_cloud_generative:
            out.append("groq")
        if (
            self.models.gemini_enabled
            and self.settings.gemini_api_key
            and self.settings.enable_cloud_generative
        ):
            out.append("gemini")
        return out

    def generate(
        self,
        prompt: str,
        *,
        operation: str = "generate",
        prefer: str | None = None,
    ) -> dict[str, Any]:
        """
        Best-effort generative call. Returns {provider, model, text} or raises
        if no provider is configured — callers must treat this as optional.
        """
        order = [prefer] if prefer else []
        order.extend(p for p in self.available_providers() if p not in order)
        last_err: Exception | None = None
        for provider in order:
            if not provider:
                continue
            try:
                if provider == "ollama":
                    return self._ollama(prompt, operation=operation)
                if provider == "groq":
                    return self._groq(prompt, operation=operation)
                if provider == "gemini":
                    return self._gemini(prompt, operation=operation)
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("Generative provider %s failed: %s", provider, exc)
                self.ledger.add(
                    ModelUsageRecord(
                        provider=provider,
                        model="unknown",
                        operation=operation,
                        error=str(exc),
                    )
                )
        raise RuntimeError(
            f"No generative provider succeeded; available={self.available_providers()} "
            f"last_error={last_err}"
        )

    def _ollama(self, prompt: str, *, operation: str) -> dict[str, Any]:
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/generate"
        payload = {
            "model": self.models.ollama_model,
            "prompt": prompt,
            "stream": False,
        }
        resp = self._client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        text = str(data.get("response") or "")
        self.ledger.add(
            ModelUsageRecord(
                provider="ollama",
                model=self.models.ollama_model,
                operation=operation,
                cost_usd=0.0,
            )
        )
        return {"provider": "ollama", "model": self.models.ollama_model, "text": text}

    def _groq(self, prompt: str, *, operation: str) -> dict[str, Any]:
        assert self.settings.groq_api_key
        resp = self._client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.groq_api_key}"},
            json={
                "model": self.models.groq_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage") or {}
        self.ledger.add(
            ModelUsageRecord(
                provider="groq",
                model=self.models.groq_model,
                operation=operation,
                input_tokens=int(usage.get("prompt_tokens") or 0),
                output_tokens=int(usage.get("completion_tokens") or 0),
                cost_usd=0.0,
            )
        )
        return {"provider": "groq", "model": self.models.groq_model, "text": text}

    def _gemini(self, prompt: str, *, operation: str) -> dict[str, Any]:
        assert self.settings.gemini_api_key
        model = self.models.gemini_model
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        resp = self._client.post(
            url,
            params={"key": self.settings.gemini_api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        resp.raise_for_status()
        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(str(p.get("text") or "") for p in parts)
        meta = data.get("usageMetadata") or {}
        self.ledger.add(
            ModelUsageRecord(
                provider="gemini",
                model=model,
                operation=operation,
                input_tokens=int(meta.get("promptTokenCount") or 0),
                output_tokens=int(meta.get("candidatesTokenCount") or 0),
                cost_usd=0.0,
            )
        )
        return {"provider": "gemini", "model": model, "text": text}
