"""extended weather metrics and bream-ready columns

Revision ID: 20260423_0007
Revises: 20260422_0006
Create Date: 2026-04-23 00:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260423_0007"
down_revision: str | None = "20260422_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE weather_snapshots
        ADD COLUMN IF NOT EXISTS cloud_cover_pct DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS precipitation_mm DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS humidity_pct DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS pressure_trend_6h_hpa DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS pressure_trend_24h_hpa DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS daylight_hours DOUBLE PRECISION NOT NULL DEFAULT 12.0,
        ADD COLUMN IF NOT EXISTS sunrise_at TIMESTAMPTZ NULL,
        ADD COLUMN IF NOT EXISTS sunset_at TIMESTAMPTZ NULL;
        """
    )
    op.execute(
        """
        ALTER TABLE weather_snapshots
        ALTER COLUMN source TYPE VARCHAR(64);
        """
    )
    op.execute(
        """
        ALTER TABLE catch_records
        ADD COLUMN IF NOT EXISTS linked_cloud_cover_pct DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS linked_precipitation_mm DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS linked_humidity_pct DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS linked_pressure_trend_24h_hpa DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        ADD COLUMN IF NOT EXISTS linked_daylight_hours DOUBLE PRECISION NOT NULL DEFAULT 12.0;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE catch_records
        DROP COLUMN IF EXISTS linked_daylight_hours,
        DROP COLUMN IF EXISTS linked_pressure_trend_24h_hpa,
        DROP COLUMN IF EXISTS linked_humidity_pct,
        DROP COLUMN IF EXISTS linked_precipitation_mm,
        DROP COLUMN IF EXISTS linked_cloud_cover_pct;
        """
    )
    op.execute(
        """
        ALTER TABLE weather_snapshots
        DROP COLUMN IF EXISTS sunset_at,
        DROP COLUMN IF EXISTS sunrise_at,
        DROP COLUMN IF EXISTS daylight_hours,
        DROP COLUMN IF EXISTS pressure_trend_24h_hpa,
        DROP COLUMN IF EXISTS pressure_trend_6h_hpa,
        DROP COLUMN IF EXISTS humidity_pct,
        DROP COLUMN IF EXISTS precipitation_mm,
        DROP COLUMN IF EXISTS cloud_cover_pct;
        """
    )
