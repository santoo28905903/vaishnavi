from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from uae_job_autopilot.db.tables import ApplicationRecord, ModelCostRecord, RunHistoryRecord, make_session_factory
from uae_job_autopilot.utils.timeutil import utcnow


class ApplicationRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    @classmethod
    def from_url(cls, database_url: str) -> ApplicationRepository:
        return cls(make_session_factory(database_url))

    def upsert_application(self, data: dict[str, Any]) -> ApplicationRecord:
        """Idempotent upsert keyed by application_key."""
        now = utcnow()
        with self._sf() as session:
            existing = session.scalar(
                select(ApplicationRecord).where(
                    ApplicationRecord.application_key == data["application_key"]
                )
            )
            if existing is None:
                row = ApplicationRecord(
                    created_at=now,
                    updated_at=now,
                    **{k: v for k, v in data.items() if hasattr(ApplicationRecord, k)},
                )
                session.add(row)
            else:
                for k, v in data.items():
                    if k in {"application_key", "id", "created_at"}:
                        continue
                    if hasattr(existing, k):
                        setattr(existing, k, v)
                existing.updated_at = now
                row = existing
            session.commit()
            session.refresh(row)
            return row

    def list_applications(self) -> list[ApplicationRecord]:
        with self._sf() as session:
            return list(session.scalars(select(ApplicationRecord)).all())

    def get_by_key(self, application_key: str) -> ApplicationRecord | None:
        with self._sf() as session:
            return session.scalar(
                select(ApplicationRecord).where(
                    ApplicationRecord.application_key == application_key
                )
            )

    def record_run(
        self,
        *,
        run_id: str,
        phase: str,
        started_at,
        finished_at,
        stats: dict[str, Any],
        notes: list[str],
        cost_usd: float,
    ) -> RunHistoryRecord:
        with self._sf() as session:
            row = session.scalar(select(RunHistoryRecord).where(RunHistoryRecord.run_id == run_id))
            if row is None:
                row = RunHistoryRecord(
                    run_id=run_id,
                    phase=phase,
                    started_at=started_at,
                    finished_at=finished_at,
                    stats_json=json.dumps(stats),
                    notes_json=json.dumps(notes),
                    cost_usd=cost_usd,
                )
                session.add(row)
            else:
                row.finished_at = finished_at
                row.stats_json = json.dumps(stats)
                row.notes_json = json.dumps(notes)
                row.cost_usd = cost_usd
            session.commit()
            session.refresh(row)
            return row

    def add_model_cost(self, *, run_id: str, usage: dict[str, Any]) -> None:
        with self._sf() as session:
            session.add(
                ModelCostRecord(
                    run_id=run_id,
                    provider=str(usage.get("provider") or ""),
                    model=str(usage.get("model") or ""),
                    operation=str(usage.get("operation") or ""),
                    input_tokens=int(usage.get("input_tokens") or 0),
                    output_tokens=int(usage.get("output_tokens") or 0),
                    cost_usd=float(usage.get("cost_usd") or 0.0),
                    cached=bool(usage.get("cached") or False),
                    created_at=utcnow(),
                )
            )
            session.commit()
