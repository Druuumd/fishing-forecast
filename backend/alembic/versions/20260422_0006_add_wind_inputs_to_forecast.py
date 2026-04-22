"""add wind fields to weather and catches

Revision ID: 20260422_0006
Revises: 20260421_0005
Create Date: 2026-04-22 00:10:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260422_0006"
down_revision: str | None = "20260421_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE weather_snapshots
        ADD COLUMN IF NOT EXISTS wind_speed_m_s DOUBLE PRECISION NOT NULL DEFAULT 3.0;
        """
    )
    op.execute(
        """
        ALTER TABLE weather_snapshots
        ADD COLUMN IF NOT EXISTS wind_direction_deg DOUBLE PRECISION NOT NULL DEFAULT 180.0;
        """
    )
    op.execute(
        """
        ALTER TABLE catch_records
        ADD COLUMN IF NOT EXISTS linked_wind_speed_m_s DOUBLE PRECISION NOT NULL DEFAULT 3.0;
        """
    )
    op.execute(
        """
        ALTER TABLE catch_records
        ADD COLUMN IF NOT EXISTS linked_wind_direction_deg DOUBLE PRECISION NOT NULL DEFAULT 180.0;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE catch_records DROP COLUMN IF EXISTS linked_wind_direction_deg;")
    op.execute("ALTER TABLE catch_records DROP COLUMN IF EXISTS linked_wind_speed_m_s;")
    op.execute("ALTER TABLE weather_snapshots DROP COLUMN IF EXISTS wind_direction_deg;")
    op.execute("ALTER TABLE weather_snapshots DROP COLUMN IF EXISTS wind_speed_m_s;")
