"""create user_consents table

Revision ID: 20260421_0005
Revises: 20260421_0004
Create Date: 2026-04-21 14:05:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260421_0005"
down_revision: str | None = "20260421_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_consents (
            user_id VARCHAR(128) PRIMARY KEY,
            geo_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            push_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            analytics_allowed BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMPTZ NOT NULL
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_consents_updated_at ON user_consents (updated_at);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_user_consents_updated_at;")
    op.execute("DROP TABLE IF EXISTS user_consents;")
