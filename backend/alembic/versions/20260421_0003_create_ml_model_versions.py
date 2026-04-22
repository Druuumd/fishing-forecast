"""create ml_model_versions table

Revision ID: 20260421_0003
Revises: 20260421_0002
Create Date: 2026-04-21 09:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260421_0003"
down_revision: str | None = "20260421_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ml_model_versions (
            id VARCHAR(32) PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL,
            train_rows INTEGER NOT NULL,
            species_bias_json TEXT NOT NULL,
            metrics_json TEXT NOT NULL
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_ml_model_versions_created_at ON ml_model_versions (created_at);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ml_model_versions_created_at;")
    op.execute("DROP TABLE IF EXISTS ml_model_versions;")
