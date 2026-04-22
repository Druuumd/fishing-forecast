from datetime import datetime

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.models import UserConsentModel
from app.schemas import ConsentRecord, ConsentUpdate


class ConsentRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def upsert(self, user_id: str, payload: ConsentUpdate, updated_at: datetime) -> ConsentRecord:
        with Session(self._engine) as session:
            existing = session.get(UserConsentModel, user_id)
            if existing is None:
                existing = UserConsentModel(
                    user_id=user_id,
                    geo_allowed=payload.geo_allowed,
                    push_allowed=payload.push_allowed,
                    analytics_allowed=payload.analytics_allowed,
                    updated_at=updated_at,
                )
                session.add(existing)
            else:
                existing.geo_allowed = payload.geo_allowed
                existing.push_allowed = payload.push_allowed
                existing.analytics_allowed = payload.analytics_allowed
                existing.updated_at = updated_at
            session.commit()
            return ConsentRecord(
                user_id=existing.user_id,
                geo_allowed=existing.geo_allowed,
                push_allowed=existing.push_allowed,
                analytics_allowed=existing.analytics_allowed,
                updated_at=existing.updated_at,
            )

    def get(self, user_id: str) -> ConsentRecord | None:
        with Session(self._engine) as session:
            row = session.get(UserConsentModel, user_id)
        if row is None:
            return None
        return ConsentRecord(
            user_id=row.user_id,
            geo_allowed=row.geo_allowed,
            push_allowed=row.push_allowed,
            analytics_allowed=row.analytics_allowed,
            updated_at=row.updated_at,
        )

    def delete(self, user_id: str) -> bool:
        with Session(self._engine) as session:
            row = session.get(UserConsentModel, user_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
        return True
