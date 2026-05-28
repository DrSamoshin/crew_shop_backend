"""add subscription frequency column

Revision ID: f8b6a35b75ea
Revises: a7e3733547a5
Create Date: 2026-05-28 19:18:53.968511+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8b6a35b75ea"
down_revision: str | Sequence[str] | None = "a7e3733547a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("subscriptions", sa.Column("frequency", sa.String(length=20), nullable=False))
    op.create_check_constraint(
        op.f("ck_subscriptions_frequency"),
        "subscriptions",
        "frequency IN ('weekly', 'biweekly', 'monthly')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_subscriptions_frequency"), "subscriptions", type_="check")
    op.drop_column("subscriptions", "frequency")
