from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class ApplicationRecord(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("application_key", name="uq_application_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    employer: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    location: Mapped[str] = mapped_column(String(256), default="")
    application_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="")
    source_job_id: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(
        String(64), default="prepared"
    )  # prepared|rejected|blocked|applied|submission_unverified|dry_run|...
    decision: Mapped[str] = mapped_column(String(64), default="")
    resume_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    visa_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ats_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ats_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    sponsorship_label: Mapped[str] = mapped_column(String(64), default="unknown")
    sponsorship_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    resume_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cover_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resume_pdf_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cover_pdf_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Phase 5 — submission evidence
    channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    apply_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmation_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmation_reference: Mapped[str | None] = mapped_column(String(256), nullable=True)
    confirmation_evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    screening_answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    checklist_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_history_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    block_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunHistoryRecord(Base):
    __tablename__ = "run_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    phase: Mapped[str] = mapped_column(String(32), default="phase3")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stats_json: Mapped[str] = mapped_column(Text, default="{}")
    notes_json: Mapped[str] = mapped_column(Text, default="[]")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)


class ModelCostRecord(Base):
    __tablename__ = "model_costs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(128), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    operation: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RunLockRecord(Base):
    """Named concurrency lock for cloud pipeline runs."""

    __tablename__ = "run_locks"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    owner: Mapped[str] = mapped_column(String(128), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meta_json: Mapped[str] = mapped_column(Text, default="{}")


class CheckpointRecord(Base):
    """Resumable stage checkpoints for a pipeline run_id."""

    __tablename__ = "run_checkpoints"
    __table_args__ = (UniqueConstraint("run_id", "stage", name="uq_run_stage"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # pending|running|done|failed|skipped
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def make_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, future=True, connect_args=connect_args)


def _ensure_sqlite_application_columns(engine) -> None:
    """
    create_all does not ALTER existing SQLite tables. Add Phase 5 columns when missing
    so local DBs created in Phase 3/4 keep working without a manual migration step.
    Postgres should use Alembic (revision 20261024_0003).
    """
    if engine.dialect.name != "sqlite":
        return
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "applications" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("applications")}
    alters: list[str] = []
    wanted = {
        "channel_id": "VARCHAR(64)",
        "apply_method": "VARCHAR(64)",
        "submitted_at": "DATETIME",
        "confirmation_verified": "BOOLEAN DEFAULT 0",
        "confirmation_reference": "VARCHAR(256)",
        "confirmation_evidence_json": "TEXT",
        "screening_answers_json": "TEXT",
        "checklist_json": "TEXT",
        "retry_history_json": "TEXT",
        "attempt_count": "INTEGER DEFAULT 0",
        "block_reason": "TEXT",
    }
    for col, ddl in wanted.items():
        if col not in existing:
            alters.append(f"ALTER TABLE applications ADD COLUMN {col} {ddl}")
    if not alters:
        return
    with engine.begin() as conn:
        for stmt in alters:
            conn.execute(text(stmt))


def make_session_factory(database_url: str):
    engine = make_engine(database_url)
    Base.metadata.create_all(engine)
    _ensure_sqlite_application_columns(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
