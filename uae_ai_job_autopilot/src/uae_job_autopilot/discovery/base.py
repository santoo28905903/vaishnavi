from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

import httpx

from uae_job_autopilot.config import SearchProfile, SourceConfig
from uae_job_autopilot.domain.models import AdapterFetchResult


class SourceAdapter(ABC):
    """Independent source adapter. Must never invent jobs."""

    name: str

    @abstractmethod
    def fetch(
        self,
        *,
        client: httpx.Client,
        profile: SearchProfile,
        source_cfg: SourceConfig,
        dry_run: bool = False,
    ) -> AdapterFetchResult:
        raise NotImplementedError


class SupportsName(Protocol):
    name: str
