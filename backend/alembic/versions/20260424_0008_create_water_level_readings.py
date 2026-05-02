"""create water_level_readings table

Revision ID: 20260424_0008
Revises: 20260423_0007
Create Date: 2026-04-24 00:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260424_0008"
down_revision: str | None = "20260423_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS water_level_readings (
            day DATE PRIMARY KEY,
            level_m DOUBLE PRECISION NOT NULL,
            inflow_m3s DOUBLE PRECISION NULL,
            outflow_m3s DOUBLE PRECISION NULL,
            source VARCHAR(64) NOT NULL,
            note TEXT NULL,
            recorded_at TIMESTAMPTZ NOT NULL
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_water_level_readings_recorded_at
        ON water_level_readings (recorded_at);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_water_level_readings_recorded_at;")
    op.execute("DROP TABLE IF EXISTS water_level_readings;")
