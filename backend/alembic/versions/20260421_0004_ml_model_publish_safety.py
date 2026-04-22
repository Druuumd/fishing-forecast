"""add ml model publish safety fields

Revision ID: 20260421_0004
Revises: 20260421_0003
Create Date: 2026-04-21 09:35:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260421_0004"
down_revision: str | None = "20260421_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE ml_model_versions ADD COLUMN IF NOT EXISTS smoke_passed BOOLEAN NOT NULL DEFAULT FALSE;")
    op.execute("ALTER TABLE ml_model_versions ADD COLUMN IF NOT EXISTS smoke_report_json TEXT NOT NULL DEFAULT '{}';")
    op.execute("ALTER TABLE ml_model_versions ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT FALSE;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_ml_model_versions_is_active ON ml_model_versions (is_active);")

    op.execute("UPDATE ml_model_versions SET smoke_passed = TRUE WHERE smoke_passed IS DISTINCT FROM TRUE;")
    op.execute(
        """
        UPDATE ml_model_versions
        SET is_active = TRUE
        WHERE id = (
            SELECT id
            FROM ml_model_versions
            ORDER BY created_at DESC
            LIMIT 1
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ml_model_versions_is_active;")
    op.execute("ALTER TABLE ml_model_versions DROP COLUMN IF EXISTS is_active;")
    op.execute("ALTER TABLE ml_model_versions DROP COLUMN IF EXISTS smoke_report_json;")
    op.execute("ALTER TABLE ml_model_versions DROP COLUMN IF EXISTS smoke_passed;")
