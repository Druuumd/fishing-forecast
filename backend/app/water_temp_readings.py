"""User-submitted water-temperature profile readings.

Anglers submit a (surface_temp, thermocline_depth, below_thermocline_temp)
tuple at a GPS point. We validate aggressively before persisting:
  * GPS within reservoir bbox (rejects accidental submissions from
    elsewhere — common after Auto-Geo on phone)
  * Surface temp 0–30°C (Krasnoyarsk reservoir realistic envelope)
  * Below-thermocline temp 1–10°C and STRICTLY less than surface
  * Thermocline depth 1–60 m (max reservoir depth ~100m, but practical
    sonar reach is ~60 m)
  * measured_at not in the future, not older than 30 days (fresh data only)

Auto-zone detection: simple lat/lon → bay mapping by distance to bay
center. Returns None if outside any bay (point on open main channel
also counts as 'main_channel' since that's the registered zone code).

The validator returns a structured ValidationResult with field-level
errors so the UI can highlight individual inputs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import Engine, desc, select
from sqlalchemy.orm import Session

from app.models import WaterTempReadingModel
from app.weather_ingest import BAY_CENTERS


# Bounding box for Krasnoyarsk reservoir (generous — covers entire 388km
# stretch from Sayanogorsk in the south to Divnogorsk dam in the north).
BBOX_MIN_LAT, BBOX_MAX_LAT = 53.0, 56.0
BBOX_MIN_LON, BBOX_MAX_LON = 90.5, 93.5

# Acceptable measurement window.
MIN_SURFACE_TEMP_C, MAX_SURFACE_TEMP_C = 0.0, 30.0
MIN_BELOW_TEMP_C, MAX_BELOW_TEMP_C = 1.0, 10.0
MIN_THERMOCLINE_DEPTH_M, MAX_THERMOCLINE_DEPTH_M = 1.0, 60.0
MAX_AGE_DAYS = 30


@dataclass
class WaterTempReading:
    id: str
    user_id: str
    measured_at: datetime
    latitude: float
    longitude: float
    zone: str | None
    surface_temp_c: float
    thermocline_depth_m: float | None
    below_thermocline_temp_c: float | None
    instrument: str | None
    note: str | None
    created_at: datetime


@dataclass
class ValidationResult:
    valid: bool
    errors: dict[str, str] = field(default_factory=dict)


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def detect_zone(latitude: float, longitude: float) -> str | None:
    """Map a GPS point to the nearest bay code (or None if too far).

    Returns the bay whose centre is closest within 25 km. If the point is
    farther than 25 km from any bay, returns 'main_channel' as a generic
    "open water" zone (the reservoir is long; many points fall between
    named bays).
    """
    if not (BBOX_MIN_LAT <= latitude <= BBOX_MAX_LAT
            and BBOX_MIN_LON <= longitude <= BBOX_MAX_LON):
        return None
    best_code = None
    best_dist = float("inf")
    for code, (lat, lon) in BAY_CENTERS.items():
        d = _haversine_km(latitude, longitude, lat, lon)
        if d < best_dist:
            best_dist = d
            best_code = code
    if best_dist <= 25.0:
        return best_code
    return "main_channel"


def validate_reading(
    *,
    measured_at: datetime,
    latitude: float,
    longitude: float,
    surface_temp_c: float,
    thermocline_depth_m: float | None,
    below_thermocline_temp_c: float | None,
    now: datetime | None = None,
) -> ValidationResult:
    errs: dict[str, str] = {}
    now = now or datetime.now(UTC)

    if measured_at > now + timedelta(minutes=5):
        errs["measured_at"] = "Время замера в будущем."
    if measured_at < now - timedelta(days=MAX_AGE_DAYS):
        errs["measured_at"] = f"Замер старше {MAX_AGE_DAYS} дней."

    if not (BBOX_MIN_LAT <= latitude <= BBOX_MAX_LAT):
        errs["latitude"] = (
            f"Широта вне диапазона водохранилища "
            f"({BBOX_MIN_LAT:.1f}…{BBOX_MAX_LAT:.1f})."
        )
    if not (BBOX_MIN_LON <= longitude <= BBOX_MAX_LON):
        errs["longitude"] = (
            f"Долгота вне диапазона водохранилища "
            f"({BBOX_MIN_LON:.1f}…{BBOX_MAX_LON:.1f})."
        )

    if not (MIN_SURFACE_TEMP_C <= surface_temp_c <= MAX_SURFACE_TEMP_C):
        errs["surface_temp_c"] = (
            f"Поверхностная температура должна быть "
            f"{MIN_SURFACE_TEMP_C:g}…{MAX_SURFACE_TEMP_C:g} °C."
        )

    if thermocline_depth_m is not None:
        if not (MIN_THERMOCLINE_DEPTH_M <= thermocline_depth_m <= MAX_THERMOCLINE_DEPTH_M):
            errs["thermocline_depth_m"] = (
                f"Глубина термоклина должна быть "
                f"{MIN_THERMOCLINE_DEPTH_M:g}…{MAX_THERMOCLINE_DEPTH_M:g} м."
            )

    if below_thermocline_temp_c is not None:
        if not (MIN_BELOW_TEMP_C <= below_thermocline_temp_c <= MAX_BELOW_TEMP_C):
            errs["below_thermocline_temp_c"] = (
                f"Температура под термоклином должна быть "
                f"{MIN_BELOW_TEMP_C:g}…{MAX_BELOW_TEMP_C:g} °C."
            )
        elif "surface_temp_c" not in errs and below_thermocline_temp_c >= surface_temp_c:
            errs["below_thermocline_temp_c"] = (
                "Температура под термоклином не может быть выше поверхностной."
            )

    # If user gave depth, expect them to also give below-temp (and vice
    # versa) — otherwise the profile is incomplete and not useful for
    # later ML training.
    has_depth = thermocline_depth_m is not None
    has_below = below_thermocline_temp_c is not None
    if has_depth ^ has_below:
        missing = "below_thermocline_temp_c" if has_depth else "thermocline_depth_m"
        if missing not in errs:
            errs[missing] = (
                "Задайте оба значения (глубину и температуру) или ни одного."
            )

    return ValidationResult(valid=not errs, errors=errs)


class WaterTempReadingRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def save(self, reading: WaterTempReading) -> WaterTempReading:
        with Session(self._engine) as session:
            session.add(WaterTempReadingModel(
                id=reading.id,
                user_id=reading.user_id,
                measured_at=reading.measured_at,
                latitude=reading.latitude,
                longitude=reading.longitude,
                zone=reading.zone,
                surface_temp_c=reading.surface_temp_c,
                thermocline_depth_m=reading.thermocline_depth_m,
                below_thermocline_temp_c=reading.below_thermocline_temp_c,
                instrument=reading.instrument,
                note=reading.note,
                created_at=reading.created_at,
            ))
            session.commit()
        return reading

    def list_recent(
        self,
        *,
        zone: str | None = None,
        limit: int = 100,
        max_age_days: int = MAX_AGE_DAYS,
    ) -> list[WaterTempReading]:
        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
        with Session(self._engine) as session:
            stmt = (
                select(WaterTempReadingModel)
                .where(WaterTempReadingModel.measured_at >= cutoff)
                .order_by(desc(WaterTempReadingModel.measured_at))
                .limit(limit)
            )
            if zone:
                stmt = stmt.where(WaterTempReadingModel.zone == zone)
            rows = session.execute(stmt).scalars().all()
        return [self._to_dto(r) for r in rows]

    def list_by_user(self, user_id: str, limit: int = 50) -> list[WaterTempReading]:
        with Session(self._engine) as session:
            rows = session.execute(
                select(WaterTempReadingModel)
                .where(WaterTempReadingModel.user_id == user_id)
                .order_by(desc(WaterTempReadingModel.measured_at))
                .limit(limit)
            ).scalars().all()
        return [self._to_dto(r) for r in rows]

    @staticmethod
    def _to_dto(row: WaterTempReadingModel) -> WaterTempReading:
        return WaterTempReading(
            id=row.id,
            user_id=row.user_id,
            measured_at=row.measured_at,
            latitude=row.latitude,
            longitude=row.longitude,
            zone=row.zone,
            surface_temp_c=row.surface_temp_c,
            thermocline_depth_m=row.thermocline_depth_m,
            below_thermocline_temp_c=row.below_thermocline_temp_c,
            instrument=row.instrument,
            note=row.note,
            created_at=row.created_at,
        )


def make_reading(
    *,
    user_id: str,
    measured_at: datetime,
    latitude: float,
    longitude: float,
    surface_temp_c: float,
    thermocline_depth_m: float | None,
    below_thermocline_temp_c: float | None,
    instrument: str | None,
    note: str | None,
) -> WaterTempReading:
    return WaterTempReading(
        id=uuid4().hex,
        user_id=user_id,
        measured_at=measured_at.astimezone(UTC),
        latitude=latitude,
        longitude=longitude,
        zone=detect_zone(latitude, longitude),
        surface_temp_c=surface_temp_c,
        thermocline_depth_m=thermocline_depth_m,
        below_thermocline_temp_c=below_thermocline_temp_c,
        instrument=instrument,
        note=note,
        created_at=datetime.now(UTC),
    )
