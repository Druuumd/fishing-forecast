"""create weather_snapshots table

Revision ID: 20260421_0002
Revises: 20260420_0001
Create Date: 2026-04-21 00:20:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260421_0002"
down_revision: str | None = "20260420_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS weather_snapshots (
            day DATE PRIMARY KEY,
            air_temp_c DOUBLE PRECISION NOT NULL,
            pressure_hpa DOUBLE PRECISION NOT NULL,
            water_temp_c DOUBLE PRECISION NOT NULL,
            moon_phase DOUBLE PRECISION NOT NULL,
            source VARCHAR(32) NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_weather_snapshots_fetched_at ON weather_snapshots (fetched_at);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_weather_snapshots_fetched_at;")
    op.execute("DROP TABLE IF EXISTS weather_snapshots;")
