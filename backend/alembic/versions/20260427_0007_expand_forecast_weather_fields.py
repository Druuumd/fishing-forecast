"""expand forecast weather fields

Revision ID: 20260427_0007
Revises: 20260426_0010
Create Date: 2026-04-27 06:20:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260427_0007"
down_revision: str | None = "20260426_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE weather_snapshots ADD COLUMN IF NOT EXISTS surface_pressure_hpa DOUBLE PRECISION;")
    op.execute("ALTER TABLE weather_snapshots ADD COLUMN IF NOT EXISTS pressure_trend_24h_hpa DOUBLE PRECISION;")
    op.execute("ALTER TABLE weather_snapshots ADD COLUMN IF NOT EXISTS cloud_cover_pct DOUBLE PRECISION;")
    op.execute("ALTER TABLE weather_snapshots ADD COLUMN IF NOT EXISTS precipitation_mm DOUBLE PRECISION;")


def downgrade() -> None:
    op.execute("ALTER TABLE weather_snapshots DROP COLUMN IF EXISTS precipitation_mm;")
    op.execute("ALTER TABLE weather_snapshots DROP COLUMN IF EXISTS cloud_cover_pct;")
    op.execute("ALTER TABLE weather_snapshots DROP COLUMN IF EXISTS pressure_trend_24h_hpa;")
    op.execute("ALTER TABLE weather_snapshots DROP COLUMN IF EXISTS surface_pressure_hpa;")
