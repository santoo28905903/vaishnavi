from __future__ import annotations

import logging
import struct
from typing import Sequence

import numpy as np

from uae_job_autopilot.config import ModelsConfig, load_models_config
from uae_job_autopilot.domain.models import ModelUsageRecord
from uae_job_autopilot.models.cache import JsonFileCache
from uae_job_autopilot.models.costs import CostLedger

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Local Sentence Transformers embeddings (cloud-safe; no Ollama dependency)."""

    def __init__(
        self,
        *,
        models: ModelsConfig | None = None,
        ledger: CostLedger | None = None,
        cache: JsonFileCache | None = None,
        model: object | None = None,
    ) -> None:
        self.models = models or load_models_config()
        self.ledger = ledger or CostLedger()
        self.cache = cache or JsonFileCache("embeddings")
        self._model = model
        self.model_name = self.models.embedding_model

    def _load(self) -> object:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed(self, texts: Sequence[str], *, operation: str = "embed") -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)

        vectors: list[np.ndarray] = []
        missing_idx: list[int] = []
        missing_texts: list[str] = []
        placeholders: list[np.ndarray | None] = [None] * len(texts)

        for i, text in enumerate(texts):
            key = JsonFileCache.key_for(self.model_name, text)
            if self.models.embedding_cache:
                raw = self.cache.get_bytes(key)
                if raw is not None:
                    placeholders[i] = _bytes_to_vec(raw)
                    self.ledger.add(
                        ModelUsageRecord(
                            provider="sentence_transformers",
                            model=self.model_name,
                            operation=operation,
                            cached=True,
                            meta={"chars": len(text)},
                        )
                    )
                    continue
            missing_idx.append(i)
            missing_texts.append(text)

        if missing_texts:
            model = self._load()
            encoded = model.encode(  # type: ignore[attr-defined]
                list(missing_texts),
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            arr = np.asarray(encoded, dtype=np.float32)
            for j, i in enumerate(missing_idx):
                vec = arr[j]
                placeholders[i] = vec
                if self.models.embedding_cache:
                    key = JsonFileCache.key_for(self.model_name, missing_texts[j])
                    self.cache.set_bytes(key, _vec_to_bytes(vec))
                self.ledger.add(
                    ModelUsageRecord(
                        provider="sentence_transformers",
                        model=self.model_name,
                        operation=operation,
                        cached=False,
                        cost_usd=0.0,
                        meta={"chars": len(missing_texts[j])},
                    )
                )

        vectors = [v for v in placeholders if v is not None]
        return np.vstack(vectors)

    def similarity_0_100(self, text_a: str, text_b: str) -> float:
        """Calibrated cosine similarity on L2-normalized embeddings → 0..100."""
        mats = self.embed([text_a, text_b], operation="similarity")
        if mats.shape[0] < 2:
            return 0.0
        # Already normalized → cosine = dot
        cos = float(np.dot(mats[0], mats[1]))
        # Map [-1,1] → [0,100]; typical resume/job pairs land mid-high.
        return max(0.0, min(100.0, ((cos + 1.0) / 2.0) * 100.0))


def _vec_to_bytes(vec: np.ndarray) -> bytes:
    flat = vec.astype(np.float32).reshape(-1)
    header = struct.pack("<I", flat.size)
    return header + flat.tobytes()


def _bytes_to_vec(raw: bytes) -> np.ndarray:
    (n,) = struct.unpack("<I", raw[:4])
    return np.frombuffer(raw[4:], dtype=np.float32, count=n)
