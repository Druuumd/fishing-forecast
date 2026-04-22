import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, desc, select
from sqlalchemy.orm import Session

from app.models import CatchRecordModel, MlModelVersionModel


class MlRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_catch_records(self) -> list[CatchRecordModel]:
        with Session(self._engine) as session:
            rows = session.execute(select(CatchRecordModel).order_by(CatchRecordModel.created_at.asc())).scalars().all()
        return rows

    def save_model_version(
        self,
        train_rows: int,
        species_bias: dict[str, float],
        metrics: dict,
        smoke_passed: bool,
        smoke_report: dict,
    ) -> dict:
        model_id = uuid4().hex
        created_at = datetime.now(UTC)
        model = MlModelVersionModel(
            id=model_id,
            created_at=created_at,
            train_rows=train_rows,
            species_bias_json=json.dumps(species_bias),
            metrics_json=json.dumps(metrics),
            smoke_passed=smoke_passed,
            smoke_report_json=json.dumps(smoke_report),
            is_active=False,
        )
        with Session(self._engine) as session:
            session.add(model)
            session.commit()
        return {
            "id": model_id,
            "created_at": created_at,
            "train_rows": train_rows,
            "species_bias": species_bias,
            "metrics": metrics,
            "smoke_passed": smoke_passed,
            "smoke_report": smoke_report,
            "is_active": False,
        }

    def get_latest_model(self) -> dict | None:
        with Session(self._engine) as session:
            row = (
                session.execute(select(MlModelVersionModel).order_by(desc(MlModelVersionModel.created_at)).limit(1))
                .scalars()
                .first()
            )
        if row is None:
            return None
        return {
            "id": row.id,
            "created_at": row.created_at,
            "train_rows": row.train_rows,
            "species_bias": json.loads(row.species_bias_json),
            "metrics": json.loads(row.metrics_json),
            "smoke_passed": bool(row.smoke_passed),
            "smoke_report": json.loads(row.smoke_report_json),
            "is_active": bool(row.is_active),
        }

    def get_active_model(self) -> dict | None:
        with Session(self._engine) as session:
            row = (
                session.execute(
                    select(MlModelVersionModel)
                    .where(MlModelVersionModel.is_active.is_(True))
                    .order_by(desc(MlModelVersionModel.created_at))
                    .limit(1)
                )
                .scalars()
                .first()
            )
        if row is None:
            return None
        return {
            "id": row.id,
            "created_at": row.created_at,
            "train_rows": row.train_rows,
            "species_bias": json.loads(row.species_bias_json),
            "metrics": json.loads(row.metrics_json),
            "smoke_passed": bool(row.smoke_passed),
            "smoke_report": json.loads(row.smoke_report_json),
            "is_active": bool(row.is_active),
        }

    def activate_model(self, model_id: str) -> dict | None:
        with Session(self._engine) as session:
            candidate = session.get(MlModelVersionModel, model_id)
            if candidate is None:
                return None
            if not candidate.smoke_passed:
                return {
                    "id": candidate.id,
                    "smoke_passed": False,
                }

            session.execute(
                select(MlModelVersionModel)
                .where(MlModelVersionModel.is_active.is_(True))
                .with_for_update()
            ).scalars().all()
            session.query(MlModelVersionModel).filter(MlModelVersionModel.is_active.is_(True)).update(
                {"is_active": False}
            )
            candidate.is_active = True
            session.commit()

        return self.get_active_model()

    def get_model_by_id(self, model_id: str) -> dict | None:
        with Session(self._engine) as session:
            row = session.get(MlModelVersionModel, model_id)
        if row is None:
            return None
        return {
            "id": row.id,
            "created_at": row.created_at,
            "train_rows": row.train_rows,
            "species_bias": json.loads(row.species_bias_json),
            "metrics": json.loads(row.metrics_json),
            "smoke_passed": bool(row.smoke_passed),
            "smoke_report": json.loads(row.smoke_report_json),
            "is_active": bool(row.is_active),
        }

    def update_smoke_result(self, model_id: str, smoke_passed: bool, smoke_report: dict) -> None:
        with Session(self._engine) as session:
            row = session.get(MlModelVersionModel, model_id)
            if row is None:
                return
            row.smoke_passed = smoke_passed
            row.smoke_report_json = json.dumps(smoke_report)
            session.commit()
