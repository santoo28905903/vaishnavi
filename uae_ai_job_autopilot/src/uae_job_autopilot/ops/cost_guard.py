from __future__ import annotations

import logging

from uae_job_autopilot.models.costs import CostLedger

logger = logging.getLogger(__name__)


class CostCapExceeded(RuntimeError):
    pass


class CostGuard:
    """Stops model-heavy stages once estimated daily spend exceeds the cap."""

    def __init__(self, ledger: CostLedger, *, cap_usd: float) -> None:
        self.ledger = ledger
        self.cap_usd = float(cap_usd)

    @property
    def spent(self) -> float:
        return float(self.ledger.total_cost_usd)

    def remaining(self) -> float:
        return max(0.0, self.cap_usd - self.spent)

    def check(self, *, stage: str) -> None:
        if self.spent > self.cap_usd:
            raise CostCapExceeded(
                f"Cost cap ${self.cap_usd:.4f} exceeded at stage={stage} "
                f"(spent=${self.spent:.4f})"
            )

    def allow_model_calls(self) -> bool:
        return self.spent <= self.cap_usd
