"""anchor users to crew_auth identity

Drops the tables that made crew_shop an identity provider and anchors every user to
the platform identity issued by crew_auth through ``users.auth_user_id``.

No data migration: the service moves to a fresh database, and old
``oauth_accounts.provider_id`` values are provider subjects while crew_auth mints its
own UUIDs for the same identities — no correspondence exists to migrate.

Revision ID: d4e5f6a7b8c9
Revises: c7d8e9f0a1b2
Create Date: 2026-07-22 09:00:00.000000+00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("auth_user_id", sa.UUID(), nullable=True))
    op.create_unique_constraint("uq_users_auth_user_id", "users", ["auth_user_id"])

    op.drop_index("idx_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("oauth_accounts")


def downgrade() -> None:
    """Downgrade schema.

    Recreates both tables exactly as they were; their contents cannot be restored.
    """
    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_id", sa.String(length=255), nullable=False),
        sa.Column("provider_email", sa.String(length=255), nullable=True),
        sa.Column("provider_name", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("provider IN ('apple', 'google')", name="ck_oauth_accounts_provider"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_oauth_accounts_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_oauth_accounts"),
        sa.UniqueConstraint("provider", "provider_id", name="uq_oauth_accounts_provider"),
        sa.UniqueConstraint("user_id", name="uq_oauth_accounts_user_id"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("refresh_jti", sa.UUID(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"], unique=False)

    op.drop_constraint("uq_users_auth_user_id", "users", type_="unique")
    op.drop_column("users", "auth_user_id")
