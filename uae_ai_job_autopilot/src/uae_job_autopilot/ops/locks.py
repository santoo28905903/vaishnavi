from __future__ import annotations

import json
import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from uae_job_autopilot.db.tables import RunLockRecord
from uae_job_autopilot.utils.timeutil import ensure_aware, utcnow

logger = logging.getLogger(__name__)


class LockNotAcquired(RuntimeError):
    pass


class RunLock:
    """Database-backed concurrency lock with TTL (works on SQLite and Postgres)."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        name: str,
        owner: str,
        ttl_seconds: int = 7200,
    ) -> None:
        self._sf = session_factory
        self.name = name
        self.owner = owner
        self.ttl_seconds = ttl_seconds
        self._held = False

    def acquire(self, *, meta: dict | None = None) -> None:
        now = utcnow()
        expires = now + timedelta(seconds=self.ttl_seconds)
        with self._sf() as session:
            for row in list(session.scalars(select(RunLockRecord))):
                if ensure_aware(row.expires_at) < now:
                    session.delete(row)
            existing = session.get(RunLockRecord, self.name)
            if (
                existing is not None
                and ensure_aware(existing.expires_at) > now
                and existing.owner != self.owner
            ):
                raise LockNotAcquired(
                    f"Lock {self.name!r} held by {existing.owner} until "
                    f"{ensure_aware(existing.expires_at).isoformat()}"
                )
            if existing is None:
                session.add(
                    RunLockRecord(
                        name=self.name,
                        owner=self.owner,
                        acquired_at=now,
                        expires_at=expires,
                        meta_json=json.dumps(meta or {}),
                    )
                )
            else:
                existing.owner = self.owner
                existing.acquired_at = now
                existing.expires_at = expires
                existing.meta_json = json.dumps(meta or {})
            session.commit()
            self._held = True
            logger.info("Acquired run lock %s as %s", self.name, self.owner)

    def release(self) -> None:
        if not self._held:
            return
        with self._sf() as session:
            existing = session.get(RunLockRecord, self.name)
            if existing is not None and existing.owner == self.owner:
                session.delete(existing)
                session.commit()
                logger.info("Released run lock %s", self.name)
        self._held = False

    def __enter__(self) -> RunLock:
        self.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        self.release()


def lock_status(session_factory: sessionmaker[Session], name: str) -> dict | None:
    now = utcnow()
    with session_factory() as session:
        row = session.scalar(select(RunLockRecord).where(RunLockRecord.name == name))
        if row is None or ensure_aware(row.expires_at) <= now:
            return None
        return {
            "name": row.name,
            "owner": row.owner,
            "acquired_at": ensure_aware(row.acquired_at).isoformat(),
            "expires_at": ensure_aware(row.expires_at).isoformat(),
        }
