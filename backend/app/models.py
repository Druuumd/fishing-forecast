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
    linked_cloud_cover_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    linked_precipitation_mm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    linked_humidity_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    linked_pressure_trend_24h_hpa: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    linked_daylight_hours: Mapped[float] = mapped_column(Float, nullable=False, default=12.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WeatherSnapshotModel(Base):
    __tablename__ = "weather_snapshots"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    zone: Mapped[str] = mapped_column(String(32), primary_key=True, default="default")
    air_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    pressure_hpa: Mapped[float] = mapped_column(Float, nullable=False)
    water_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    wind_speed_m_s: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    wind_direction_deg: Mapped[float] = mapped_column(Float, nullable=False, default=180.0)
    moon_phase: Mapped[float] = mapped_column(Float, nullable=False)
    cloud_cover_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    precipitation_mm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    humidity_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pressure_trend_6h_hpa: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pressure_trend_24h_hpa: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    daylight_hours: Mapped[float] = mapped_column(Float, nullable=False, default=12.0)
    sunrise_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sunset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
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


class WaterLevelReadingModel(Base):
    __tablename__ = "water_level_readings"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    level_m: Mapped[float] = mapped_column(Float, nullable=False)
    inflow_m3s: Mapped[float | None] = mapped_column(Float, nullable=True)
    outflow_m3s: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class WaterTempReadingModel(Base):
    __tablename__ = "water_temp_readings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    zone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    surface_temp_c: Mapped[float] = mapped_column(Float, nullable=False)
    thermocline_depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    below_thermocline_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    instrument: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PushSubscriptionModel(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth_secret: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scope_zone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scope_species: Mapped[str | None] = mapped_column(String(16), nullable=True)
    conditions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    last_notified_for_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserConsentModel(Base):
    __tablename__ = "user_consents"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    geo_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    push_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    analytics_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
