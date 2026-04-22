from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class CatchRecordModel(Base):
    __tablename__ = "catch_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    species: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    caught_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    linked_weather_date: Mapped[date] = mapped_column(Date, nullable=False)
    linked_air_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    linked_pressure_hpa: Mapped[float] = mapped_column(Float, nullable=False)
    linked_water_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    linked_wind_speed_m_s: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    linked_wind_direction_deg: Mapped[float] = mapped_column(Float, nullable=False, default=180.0)
    linked_moon_phase: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WeatherSnapshotModel(Base):
    __tablename__ = "weather_snapshots"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    air_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    pressure_hpa: Mapped[float] = mapped_column(Float, nullable=False)
    water_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    wind_speed_m_s: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    wind_direction_deg: Mapped[float] = mapped_column(Float, nullable=False, default=180.0)
    moon_phase: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class MlModelVersionModel(Base):
    __tablename__ = "ml_model_versions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    train_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    species_bias_json: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    smoke_passed: Mapped[bool] = mapped_column(nullable=False, default=False)
    smoke_report_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_active: Mapped[bool] = mapped_column(nullable=False, default=False, index=True)


class UserConsentModel(Base):
    __tablename__ = "user_consents"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    geo_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    push_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    analytics_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
