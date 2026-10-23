from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from uae_job_autopilot.db.tables import CheckpointRecord
from uae_job_autopilot.utils.timeutil import utcnow

STAGES = ("discover", "evaluate", "prepare_docs", "report")


class CheckpointStore:
    def __init__(self, session_factory: sessionmaker[Session], run_id: str) -> None:
        self._sf = session_factory
        self.run_id = run_id

    def mark(
        self,
        stage: str,
        status: str,
        *,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> CheckpointRecord:
        now = utcnow()
        with self._sf() as session:
            row = session.scalar(
                select(CheckpointRecord).where(
                    CheckpointRecord.run_id == self.run_id,
                    CheckpointRecord.stage == stage,
                )
            )
            if row is None:
                row = CheckpointRecord(
                    run_id=self.run_id,
                    stage=stage,
                    status=status,
                    payload_json=json.dumps(payload or {}),
                    error=error,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.status = status
                row.payload_json = json.dumps(payload or {})
                row.error = error
                row.updated_at = now
            session.commit()
            session.refresh(row)
            return row

    def get(self, stage: str) -> CheckpointRecord | None:
        with self._sf() as session:
            return session.scalar(
                select(CheckpointRecord).where(
                    CheckpointRecord.run_id == self.run_id,
                    CheckpointRecord.stage == stage,
                )
            )

    def is_done(self, stage: str) -> bool:
        row = self.get(stage)
        return row is not None and row.status == "done"

    def load_payload(self, stage: str) -> dict[str, Any]:
        row = self.get(stage)
        if row is None:
            return {}
        try:
            data = json.loads(row.payload_json or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def all_stages(self) -> list[dict[str, Any]]:
        with self._sf() as session:
            rows = list(
                session.scalars(
                    select(CheckpointRecord).where(CheckpointRecord.run_id == self.run_id)
                )
            )
        return [
            {
                "stage": r.stage,
                "status": r.status,
                "error": r.error,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]
