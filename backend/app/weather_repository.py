from datetime import date

from sqlalchemy import Engine, desc, select
from sqlalchemy.orm import Session

from app.forecast_service import WeatherSnapshot
from app.models import WeatherSnapshotModel

DEFAULT_ZONE = "default"


class WeatherRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def upsert_snapshots(
        self,
        snapshots: list[WeatherSnapshot],
        source: str,
        fetched_at,
        zone: str = DEFAULT_ZONE,
    ) -> None:
        with Session(self._engine) as session:
            for item in snapshots:
                existing = session.get(WeatherSnapshotModel, (item.day, zone))
                if existing is None:
                    session.add(
                        WeatherSnapshotModel(
                            day=item.day,
                            zone=zone,
                            air_temp_c=item.air_temp_c,
                            pressure_hpa=item.pressure_hpa,
                            water_temp_c=item.water_temp_c,
                            wind_speed_m_s=item.wind_speed_m_s,
                            wind_direction_deg=item.wind_direction_deg,
                            moon_phase=item.moon_phase,
                            cloud_cover_pct=item.cloud_cover_pct,
                            precipitation_mm=item.precipitation_mm,
                            humidity_pct=item.humidity_pct,
                            pressure_trend_6h_hpa=item.pressure_trend_6h_hpa,
                            pressure_trend_24h_hpa=item.pressure_trend_24h_hpa,
                            daylight_hours=item.daylight_hours,
                            sunrise_at=item.sunrise,
                            sunset_at=item.sunset,
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
                    existing.cloud_cover_pct = item.cloud_cover_pct
                    existing.precipitation_mm = item.precipitation_mm
                    existing.humidity_pct = item.humidity_pct
                    existing.pressure_trend_6h_hpa = item.pressure_trend_6h_hpa
                    existing.pressure_trend_24h_hpa = item.pressure_trend_24h_hpa
                    existing.daylight_hours = item.daylight_hours
                    existing.sunrise_at = item.sunrise
                    existing.sunset_at = item.sunset
                    existing.source = source
                    existing.fetched_at = fetched_at
            session.commit()

    def get_window(
        self,
        start_day: date,
        days: int,
        zone: str = DEFAULT_ZONE,
    ) -> list[WeatherSnapshot]:
        with Session(self._engine) as session:
            rows = (
                session.execute(
                    select(WeatherSnapshotModel)
                    .where(WeatherSnapshotModel.day >= start_day)
                    .where(WeatherSnapshotModel.zone == zone)
                    .order_by(WeatherSnapshotModel.day.asc())
                    .limit(days)
                )
                .scalars()
                .all()
            )
        return [self._to_snapshot(row) for row in rows]

    def get_last_updated_at(self, zone: str = DEFAULT_ZONE):
        with Session(self._engine) as session:
            row = session.execute(
                select(WeatherSnapshotModel.fetched_at)
                .where(WeatherSnapshotModel.zone == zone)
                .order_by(desc(WeatherSnapshotModel.fetched_at))
                .limit(1)
            ).scalar_one_or_none()
        return row

    def get_window_models(
        self,
        start_day: date,
        days: int,
        zone: str = DEFAULT_ZONE,
    ) -> list[WeatherSnapshotModel]:
        with Session(self._engine) as session:
            rows = (
                session.execute(
                    select(WeatherSnapshotModel)
                    .where(WeatherSnapshotModel.day >= start_day)
                    .where(WeatherSnapshotModel.zone == zone)
                    .order_by(WeatherSnapshotModel.day.asc())
                    .limit(days)
                )
                .scalars()
                .all()
            )
        return rows

    def _to_snapshot(self, row: WeatherSnapshotModel) -> WeatherSnapshot:
        return WeatherSnapshot(
            day=row.day,
            air_temp_c=row.air_temp_c,
            pressure_hpa=row.pressure_hpa,
            water_temp_c=row.water_temp_c,
            wind_speed_m_s=row.wind_speed_m_s,
            wind_direction_deg=row.wind_direction_deg,
            moon_phase=row.moon_phase,
            cloud_cover_pct=row.cloud_cover_pct,
            precipitation_mm=row.precipitation_mm,
            humidity_pct=row.humidity_pct,
            pressure_trend_6h_hpa=row.pressure_trend_6h_hpa,
            pressure_trend_24h_hpa=row.pressure_trend_24h_hpa,
            daylight_hours=row.daylight_hours,
            sunrise=row.sunrise_at,
            sunset=row.sunset_at,
        )
