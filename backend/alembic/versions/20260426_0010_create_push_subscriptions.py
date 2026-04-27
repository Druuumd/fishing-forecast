"""create push_subscriptions with conditions_json constructor

Revision ID: 20260426_0010
Revises: 20260426_0009
Create Date: 2026-04-26 12:00:00

Subscription model is a constructor: a transport (endpoint+keys), a
scope (zone+species), and a list of compose-able conditions stored as
JSON. The dispatcher evaluates every condition against each candidate
forecast day; matching days fire a notification. Dedup is per (sub,
day) via last_notified_for_day.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260426_0010"
down_revision: str | None = "20260426_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id VARCHAR(32) PRIMARY KEY,
            user_id VARCHAR(128) NOT NULL,
            endpoint TEXT NOT NULL,
            p256dh TEXT NOT NULL,
            auth_secret TEXT NOT NULL,
            name VARCHAR(128) NULL,
            scope_zone VARCHAR(32) NULL,
            scope_species VARCHAR(16) NULL,
            conditions_json TEXT NOT NULL DEFAULT '[]',
            last_notified_for_day DATE NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT push_subscriptions_endpoint_unique UNIQUE (endpoint)
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_push_subscriptions_user_id
        ON push_subscriptions (user_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_push_subscriptions_user_id;")
    op.execute("DROP TABLE IF EXISTS push_subscriptions;")
