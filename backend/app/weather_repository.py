from datetime import date

from sqlalchemy import Engine, desc, select
from sqlalchemy.orm import Session

from app.forecast_service import WeatherSnapshot
from app.models import WeatherSnapshotModel


class WeatherRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def upsert_snapshots(self, snapshots: list[WeatherSnapshot], source: str, fetched_at) -> None:
        with Session(self._engine) as session:
            for item in snapshots:
                existing = session.get(WeatherSnapshotModel, item.day)
                if existing is None:
                    session.add(
                        WeatherSnapshotModel(
                            day=item.day,
                            air_temp_c=item.air_temp_c,
                            pressure_hpa=item.pressure_hpa,
                            water_temp_c=item.water_temp_c,
                            wind_speed_m_s=item.wind_speed_m_s,
                            wind_direction_deg=item.wind_direction_deg,
                            moon_phase=item.moon_phase,
                            source=source,
                            fetched_at=fetched_at,
                        )
                    )
                else:
                    existing.air_temp_c = item.air_temp_c
                    existing.pressure_hpa = item.pressure_hpa
                    existing.water_temp_c = item.water_temp_c
                    existing.wind_speed_m_s = item.wind_speed_m_s
                    existing.wind_direction_deg = item.wind_direction_deg
                    existing.moon_phase = item.moon_phase
                    existing.source = source
                    existing.fetched_at = fetched_at
            session.commit()

    def get_window(self, start_day: date, days: int) -> list[WeatherSnapshot]:
        with Session(self._engine) as session:
            rows = (
                session.execute(
                    select(WeatherSnapshotModel)
                    .where(WeatherSnapshotModel.day >= start_day)
                    .order_by(WeatherSnapshotModel.day.asc())
                    .limit(days)
                )
                .scalars()
                .all()
            )
        return [
            WeatherSnapshot(
                day=row.day,
                air_temp_c=row.air_temp_c,
                pressure_hpa=row.pressure_hpa,
                water_temp_c=row.water_temp_c,
                wind_speed_m_s=row.wind_speed_m_s,
                wind_direction_deg=row.wind_direction_deg,
                moon_phase=row.moon_phase,
            )
            for row in rows
        ]

    def get_last_updated_at(self):
        with Session(self._engine) as session:
            row = session.execute(
                select(WeatherSnapshotModel.fetched_at).order_by(desc(WeatherSnapshotModel.fetched_at)).limit(1)
            ).scalar_one_or_none()
        return row

    def get_window_models(self, start_day: date, days: int) -> list[WeatherSnapshotModel]:
        with Session(self._engine) as session:
            rows = (
                session.execute(
                    select(WeatherSnapshotModel)
                    .where(WeatherSnapshotModel.day >= start_day)
                    .order_by(WeatherSnapshotModel.day.asc())
                    .limit(days)
                )
                .scalars()
                .all()
            )
        return rows
