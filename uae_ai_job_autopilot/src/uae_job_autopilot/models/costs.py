from __future__ import annotations

from uae_job_autopilot.domain.models import ModelUsageRecord


class CostLedger:
    """Tracks model requests, tokens, and estimated USD cost."""

    def __init__(self) -> None:
        self.records: list[ModelUsageRecord] = []

    def add(self, record: ModelUsageRecord) -> ModelUsageRecord:
        self.records.append(record)
        return record

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost_usd for r in self.records)

    @property
    def total_input_tokens(self) -> int:
        return sum(r.input_tokens for r in self.records)

    @property
    def total_output_tokens(self) -> int:
        return sum(r.output_tokens for r in self.records)

    def estimate_jev_cost(
        self, *, input_tokens: int, cost_per_mtok_input_usd: float
    ) -> float:
        return (input_tokens / 1_000_000.0) * cost_per_mtok_input_usd
