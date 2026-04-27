"""Water level readings for Krasnoyarsk reservoir.

The reservoir operates between UMO=225.0 m (minimum, late winter drawdown)
and NPU=243.0 m (normal pool, summer). The seasonal climatology below is a
fishing-oriented approximation of long-term typical monthly levels.

Data model:
* ``WaterLevelReading`` – one point-in-time observation.
* ``WaterLevelRepository`` – DB access (upsert by day, latest, window).
* ``WaterLevelService`` – business logic: latest + 7-day trend + climatology
  fallback; consumed by the forecast service.

Official open APIs (rushydro, FAVR GIS, allrivers.info) require CAPTCHA/CSRF
so for MVP we expose an admin endpoint (``POST /v1/admin/water-level``) for
manual entry of the daily operational level. Any future scraper can just
call ``WaterLevelRepository.upsert`` the same way.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Engine, desc, select
from sqlalchemy.orm import Session

from app.models import WaterLevelReadingModel

# Krasnoyarsk reservoir reference marks (Baltic system, metres).
NPU_M: float = 243.0  # Normal pool.
UMO_M: float = 225.0  # Dead storage.

# Typical monthly averages (metres) — fishing-oriented climatology. Rough
# long-term mean of operational levels. Used only when no recent readings
# are available in DB.
SEASONAL_CLIMATOLOGY_M: dict[int, float] = {
    1: 235.5,
    2: 232.0,
    3: 229.5,
    4: 227.5,
    5: 230.5,
    6: 236.0,
    7: 240.0,
    8: 242.0,
    9: 241.5,
    10: 240.0,
    11: 238.5,
    12: 237.0,
}


@dataclass(frozen=True)
class WaterLevelReading:
    day: date
    level_m: float
    inflow_m3s: float | None = None
    outflow_m3s: float | None = None
    source: str = "manual"
    note: str | None = None
    recorded_at: datetime | None = None


@dataclass(frozen=True)
class WaterLevelState:
    """Aggregate used by the forecast service."""
    latest_level_m: float
    latest_day: date
    trend_7d_m: float  # signed delta: latest - reading_7_days_ago
    source: str
    is_fresh: bool  # True if the newest reading is ≤ 14 days old


class WaterLevelRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def upsert(self, reading: WaterLevelReading) -> WaterLevelReading:
        recorded_at = reading.recorded_at or datetime.now(UTC)
        with Session(self._engine) as session:
            existing = session.get(WaterLevelReadingModel, reading.day)
            if existing is None:
                session.add(
                    WaterLevelReadingModel(
                        day=reading.day,
                        level_m=reading.level_m,
                        inflow_m3s=reading.inflow_m3s,
                        outflow_m3s=reading.outflow_m3s,
                        source=reading.source,
                        note=reading.note,
                        recorded_at=recorded_at,
                    )
                )
            else:
                existing.level_m = reading.level_m
                existing.inflow_m3s = reading.inflow_m3s
                existing.outflow_m3s = reading.outflow_m3s
                existing.source = reading.source
                existing.note = reading.note
                existing.recorded_at = recorded_at
            session.commit()
        return WaterLevelReading(
            day=reading.day,
            level_m=reading.level_m,
            inflow_m3s=reading.inflow_m3s,
            outflow_m3s=reading.outflow_m3s,
            source=reading.source,
            note=reading.note,
            recorded_at=recorded_at,
        )

    def get_latest(self) -> WaterLevelReading | None:
        with Session(self._engine) as session:
            row = session.execute(
                select(WaterLevelReadingModel).order_by(desc(WaterLevelReadingModel.day)).limit(1)
            ).scalars().first()
        if row is None:
            return None
        return self._to_reading(row)

    def get_window(self, start_day: date, end_day: date) -> list[WaterLevelReading]:
        with Session(self._engine) as session:
            rows = session.execute(
                select(WaterLevelReadingModel)
                .where(WaterLevelReadingModel.day >= start_day)
                .where(WaterLevelReadingModel.day <= end_day)
                .order_by(WaterLevelReadingModel.day.asc())
            ).scalars().all()
        return [self._to_reading(row) for row in rows]

    def _to_reading(self, row: WaterLevelReadingModel) -> WaterLevelReading:
        return WaterLevelReading(
            day=row.day,
            level_m=row.level_m,
            inflow_m3s=row.inflow_m3s,
            outflow_m3s=row.outflow_m3s,
            source=row.source,
            note=row.note,
            recorded_at=row.recorded_at,
        )


class WaterLevelService:
    # Reading is considered "fresh" enough to skip climatology if newer than this.
    FRESH_WINDOW_DAYS = 14

    def __init__(self, repository: WaterLevelRepository) -> None:
        self._repository = repository

    def current_state(self, today: date | None = None) -> WaterLevelState:
        today = today or datetime.now(UTC).date()
        latest = self._repository.get_latest()
        window_start = today - timedelta(days=10)
        window_end = today + timedelta(days=2)
        window = self._repository.get_window(window_start, window_end)

        if latest is None or (today - latest.day).days > self.FRESH_WINDOW_DAYS:
            # Climatology fallback.
            level = self.climatology_for(today)
            trend = self.climatology_for(today) - self.climatology_for(today - timedelta(days=7))
            source = "climatology"
            return WaterLevelState(
                latest_level_m=round(level, 2),
                latest_day=today,
                trend_7d_m=round(trend, 2),
                source=source,
                is_fresh=False,
            )

        # Compute 7-day trend from DB if possible; fall back to climatology delta.
        seven_days_ago = latest.day - timedelta(days=7)
        prior = None
        for item in window:
            if item.day <= seven_days_ago:
                prior = item
        if prior is not None:
            trend = latest.level_m - prior.level_m
        else:
            trend = latest.level_m - self.climatology_for(seven_days_ago)

        return WaterLevelState(
            latest_level_m=round(latest.level_m, 2),
            latest_day=latest.day,
            trend_7d_m=round(trend, 2),
            source=latest.source,
            is_fresh=True,
        )

    @staticmethod
    def climatology_for(day: date) -> float:
        """Interpolate between monthly averages using day-of-month fraction."""
        this_month = day.month
        base = SEASONAL_CLIMATOLOGY_M[this_month]
        # Interpolate to next month value by fraction of month elapsed.
        next_month = 1 if this_month == 12 else this_month + 1
        target = SEASONAL_CLIMATOLOGY_M[next_month]
        # Smooth with sine for gentle transitions.
        try:
            days_in_month = (date(day.year if this_month < 12 else day.year + 1, next_month, 1)
                             - date(day.year, this_month, 1)).days
        except ValueError:
            days_in_month = 30
        frac = min(1.0, max(0.0, (day.day - 1) / days_in_month))
        weight = 0.5 * (1 - math.cos(math.pi * frac))
        return base + (target - base) * weight


@dataclass(frozen=True)
class WaterLevelIngestResult:
    status: str  # "ok" | "no_source" | "no_data" | "stale_observation"
    reason: str | None = None
    saved: WaterLevelReading | None = None


class WaterLevelIngestService:
    """Bridge between an external source and the repository.

    On each call, asks the configured source for a fresh observation.
    If the source returns None (network failure, blocked, parse error)
    we don't touch the DB — manual admin entries and climatology
    fallback continue to work. If the source returns a reading older
    than what's already in DB, we skip the upsert.
    """

    def __init__(
        self,
        source,
        repository: "WaterLevelRepository",
    ) -> None:
        self._source = source
        self._repository = repository

    def ingest(self) -> WaterLevelIngestResult:
        if self._source is None:
            return WaterLevelIngestResult(status="no_source", reason="scraping disabled")
        observation = self._source.fetch()
        if observation is None:
            return WaterLevelIngestResult(status="no_data", reason="source returned None")
        latest = self._repository.get_latest()
        if latest is not None and latest.day > observation.day:
            return WaterLevelIngestResult(
                status="stale_observation",
                reason=f"DB has {latest.day} > scraped {observation.day}",
            )
        reading = WaterLevelReading(
            day=observation.day,
            level_m=observation.level_m,
            inflow_m3s=observation.inflow_m3s,
            outflow_m3s=observation.outflow_m3s,
            source=observation.source,
            note=observation.note,
        )
        saved = self._repository.upsert(reading)
        return WaterLevelIngestResult(status="ok", saved=saved)
