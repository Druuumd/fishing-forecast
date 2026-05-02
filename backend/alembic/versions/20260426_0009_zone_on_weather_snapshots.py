"""add zone column to weather_snapshots

Revision ID: 20260426_0009
Revises: 20260424_0008
Create Date: 2026-04-26 00:00:00

The reservoir is split into named bays (Сыда, Дербино, Бирюса, главное
русло). Open-Meteo can give us a separate weather snapshot per bay
center, which replaces the heuristic Δ°C offset in zone_profile with
real per-zone weather data. We extend the primary key from (day) to
(day, zone). Existing rows are migrated to zone='default'.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260426_0009"
down_revision: str | None = "20260424_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE weather_snapshots
        ADD COLUMN IF NOT EXISTS zone VARCHAR(32) NOT NULL DEFAULT 'default';
        """
    )
    op.execute("ALTER TABLE weather_snapshots DROP CONSTRAINT IF EXISTS weather_snapshots_pkey;")
    op.execute(
        "ALTER TABLE weather_snapshots ADD CONSTRAINT weather_snapshots_pkey PRIMARY KEY (day, zone);"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_weather_snapshots_zone_day
        ON weather_snapshots (zone, day);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_weather_snapshots_zone_day;")
    op.execute("ALTER TABLE weather_snapshots DROP CONSTRAINT IF EXISTS weather_snapshots_pkey;")
    # Keep only one row per day before reverting PK to (day) — pick zone='default'.
    op.execute("DELETE FROM weather_snapshots WHERE zone <> 'default';")
    op.execute(
        "ALTER TABLE weather_snapshots ADD CONSTRAINT weather_snapshots_pkey PRIMARY KEY (day);"
    )
    op.execute("ALTER TABLE weather_snapshots DROP COLUMN IF EXISTS zone;")
