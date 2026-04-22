from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.models import Base, CatchRecordModel
from app.schemas import CatchRecord


class CatchRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def init_schema(self) -> None:
        Base.metadata.create_all(self._engine)

    def ping(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def save(self, record: CatchRecord) -> CatchRecord:
        model = CatchRecordModel(**record.model_dump())
        with Session(self._engine) as session:
            session.add(model)
            session.commit()
        return record

    def delete_by_user_id(self, user_id: str) -> int:
        with Session(self._engine) as session:
            deleted = session.query(CatchRecordModel).filter(CatchRecordModel.user_id == user_id).delete()
            session.commit()
        return int(deleted)

    def list_by_user_id(self, user_id: str) -> list[CatchRecord]:
        with Session(self._engine) as session:
            rows = session.query(CatchRecordModel).filter(CatchRecordModel.user_id == user_id).all()
        return [CatchRecord.model_validate(row, from_attributes=True) for row in rows]
