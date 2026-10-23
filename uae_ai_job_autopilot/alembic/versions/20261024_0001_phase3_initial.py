"""phase3 initial tables

Revision ID: 20261024_0001
Revises:
Create Date: 2026-10-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_key", sa.String(length=64), nullable=False),
        sa.Column("employer", sa.String(length=256), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("location", sa.String(length=256), nullable=False),
        sa.Column("application_url", sa.String(length=1024), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_job_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("resume_score", sa.Float(), nullable=True),
        sa.Column("visa_score", sa.Float(), nullable=True),
        sa.Column("ats_score", sa.Float(), nullable=True),
        sa.Column("ats_passed", sa.Boolean(), nullable=False),
        sa.Column("sponsorship_label", sa.String(length=64), nullable=False),
        sa.Column("sponsorship_confirmed", sa.Boolean(), nullable=False),
        sa.Column("resume_version", sa.String(length=128), nullable=True),
        sa.Column("cover_version", sa.String(length=128), nullable=True),
        sa.Column("resume_pdf_path", sa.String(length=1024), nullable=True),
        sa.Column("cover_pdf_path", sa.String(length=1024), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_key", name="uq_application_key"),
    )
    op.create_index("ix_applications_application_key", "applications", ["application_key"])

    op.create_table(
        "run_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stats_json", sa.Text(), nullable=False),
        sa.Column("notes_json", sa.Text(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )

    op.create_table(
        "model_costs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_costs_run_id", "model_costs", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_model_costs_run_id", table_name="model_costs")
    op.drop_table("model_costs")
    op.drop_table("run_history")
    op.drop_index("ix_applications_application_key", table_name="applications")
    op.drop_table("applications")
