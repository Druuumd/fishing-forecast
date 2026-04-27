"""create water_temp_readings (user-submitted thermal profiles)

Revision ID: 20260427_0011
Revises: 20260427_0007
Create Date: 2026-04-27 17:00:00

User-submitted measurements of the temperature column (surface temp +
optional thermocline depth + below-thermocline temp), tied to GPS
coordinates. Will be aggregated and used to:
  * Replace heuristic thermocline depth with observed values when fresh
    measurements exist for the zone.
  * Train a regression model (depth = f(zone, surface_temp, season,
    recent_wind, ...)).

Validation lives in the API layer (range checks + bbox + freshness);
DB only enforces NOT NULL + indices.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260427_0011"
down_revision: str | None = "20260427_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS water_temp_readings (
            id VARCHAR(32) PRIMARY KEY,
            user_id VARCHAR(128) NOT NULL,
            measured_at TIMESTAMPTZ NOT NULL,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            zone VARCHAR(32) NULL,
            surface_temp_c DOUBLE PRECISION NOT NULL,
            thermocline_depth_m DOUBLE PRECISION NULL,
            below_thermocline_temp_c DOUBLE PRECISION NULL,
            instrument VARCHAR(64) NULL,
            note TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_water_temp_readings_measured_at
        ON water_temp_readings (measured_at);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_water_temp_readings_zone_measured_at
        ON water_temp_readings (zone, measured_at);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_water_temp_readings_user_id
        ON water_temp_readings (user_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_water_temp_readings_zone_measured_at;")
    op.execute("DROP INDEX IF EXISTS ix_water_temp_readings_measured_at;")
    op.execute("DROP INDEX IF EXISTS ix_water_temp_readings_user_id;")
    op.execute("DROP TABLE IF EXISTS water_temp_readings;")
