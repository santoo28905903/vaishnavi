"""phase5 application submission evidence columns

Revision ID: 20261024_0003
Revises: 20261024_0002
Create Date: 2026-10-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_0003"
down_revision: Union[str, None] = "20261024_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("channel_id", sa.String(length=64), nullable=True))
    op.add_column("applications", sa.Column("apply_method", sa.String(length=64), nullable=True))
    op.add_column(
        "applications", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "applications",
        sa.Column("confirmation_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "applications", sa.Column("confirmation_reference", sa.String(length=256), nullable=True)
    )
    op.add_column("applications", sa.Column("confirmation_evidence_json", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("screening_answers_json", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("checklist_json", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("retry_history_json", sa.Text(), nullable=True))
    op.add_column(
        "applications",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("applications", sa.Column("block_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "block_reason")
    op.drop_column("applications", "attempt_count")
    op.drop_column("applications", "retry_history_json")
    op.drop_column("applications", "checklist_json")
    op.drop_column("applications", "screening_answers_json")
    op.drop_column("applications", "confirmation_evidence_json")
    op.drop_column("applications", "confirmation_reference")
    op.drop_column("applications", "confirmation_verified")
    op.drop_column("applications", "submitted_at")
    op.drop_column("applications", "apply_method")
    op.drop_column("applications", "channel_id")
