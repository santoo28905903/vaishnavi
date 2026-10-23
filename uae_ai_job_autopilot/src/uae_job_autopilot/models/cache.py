from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from uae_job_autopilot.config import DEFAULT_DATA_DIR

logger = logging.getLogger(__name__)


class JsonFileCache:
    """Simple content-addressed JSON/binary cache under data/cache/."""

    def __init__(self, namespace: str, *, root: Path | None = None) -> None:
        self.root = (root or DEFAULT_DATA_DIR / "cache") / namespace
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key_for(*parts: Any) -> str:
        blob = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get_json(self, key: str) -> dict[str, Any] | None:
        path = self.root / f"{key}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            logger.warning("Corrupt cache entry %s", path)
            return None

    def set_json(self, key: str, value: dict[str, Any]) -> None:
        path = self.root / f"{key}.json"
        path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")

    def get_bytes(self, key: str) -> bytes | None:
        path = self.root / f"{key}.bin"
        if not path.exists():
            return None
        return path.read_bytes()

    def set_bytes(self, key: str, value: bytes) -> None:
        path = self.root / f"{key}.bin"
        path.write_bytes(value)
