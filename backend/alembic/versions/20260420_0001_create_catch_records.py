"""create catch_records table

Revision ID: 20260420_0001
Revises:
Create Date: 2026-04-20 19:20:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260420_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catch_records (
            id VARCHAR(32) PRIMARY KEY,
            user_id VARCHAR(128) NOT NULL,
            species VARCHAR(16) NOT NULL,
            score DOUBLE PRECISION NOT NULL,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            note TEXT NULL,
            caught_at TIMESTAMPTZ NOT NULL,
            linked_weather_date DATE NOT NULL,
            linked_air_temp_c DOUBLE PRECISION NOT NULL,
            linked_pressure_hpa DOUBLE PRECISION NOT NULL,
            linked_water_temp_c DOUBLE PRECISION NOT NULL,
            linked_moon_phase DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_catch_records_user_id ON catch_records (user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_catch_records_species ON catch_records (species);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_catch_records_caught_at ON catch_records (caught_at);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_catch_records_caught_at;")
    op.execute("DROP INDEX IF EXISTS ix_catch_records_species;")
    op.execute("DROP INDEX IF EXISTS ix_catch_records_user_id;")
    op.execute("DROP TABLE IF EXISTS catch_records;")
