"""create recognition history

Revision ID: 0001_initial
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recognitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("spell", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_recognitions_spell", "recognitions", ["spell"])


def downgrade() -> None:
    op.drop_index("ix_recognitions_spell", table_name="recognitions")
    op.drop_table("recognitions")
