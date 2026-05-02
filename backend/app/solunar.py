"""Solunar major/minor windows computed from real lunar ephemeris.

Replaces the approximate moon-transit math previously in
``forecast_service.best_hours()`` with proper ephemeris computations
via PyEphem. Output has the same shape as before so the score-card
UI keeps working unchanged; values are now physically accurate.

Major windows (±1h):
  * Upper transit — moon at observer's meridian (overhead). Strongest
    solunar pull → traditional "лунный зенит" peak.
  * Lower transit (anti-transit) — moon underfoot, half a lunar day later.

Minor windows (±30min):
  * Moonrise — moon crossing horizon ascending.
  * Moonset  — moon crossing horizon descending.

Quality multiplier ∈ [0, 1] — derived from current illumination
percentage. Peaks at new (illumination 0%) and full (100%); valley at
first/last quarter (50% illumination), reflecting the canonical
solunar-tables intuition that gravitational alignment matters more
than crescent thickness.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

import ephem

logger = logging.getLogger("fishing_forecast.solunar")


def _to_utc(ephem_date) -> datetime:
    """Convert an ephem.Date (UTC by definition) to a tz-aware UTC datetime."""
    return ephem_date.datetime().replace(tzinfo=UTC)


def compute_solunar_periods(
    *,
    target_date: date,
    lat: float,
    lon: float,
    elevation_m: float = 234.0,
) -> dict:
    """Compute solunar windows centred around ``target_date`` (UTC).

    target_date is interpreted as a UTC calendar day; we search the
    next-event APIs from its midnight and accept events within a
    forward window of about a lunar day. The frontend converts the
    returned UTC datetimes to the user's local timezone for display.

    Returns
    -------
    dict
      ``major``  list[dict] of ``{start, end, label}`` (each window 2h).
      ``minor``  list[dict] of ``{start, end, label}`` (each window 1h).
      ``quality`` float in [0, 1]: 1 at full or new moon, 0 at quarters.
    """
    obs = ephem.Observer()
    obs.lat = str(lat)
    obs.lon = str(lon)
    obs.elevation = float(elevation_m)
    # Disable atmospheric refraction for repeatability (tests rely on
    # deterministic output; effect on transit time is sub-second anyway).
    obs.pressure = 0
    obs.horizon = "0"

    # Anchor at start-of-day UTC.
    start_dt = datetime(
        target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=UTC
    )
    obs.date = ephem.Date(start_dt.strftime("%Y/%m/%d %H:%M:%S"))

    moon = ephem.Moon()
    moon.compute(obs)

    major: list[dict] = []
    minor: list[dict] = []

    # -- Major: upper + lower transits -----------------------------------
    try:
        upper = obs.next_transit(moon)
        c = _to_utc(upper)
        major.append({
            "start": c - timedelta(hours=1),
            "end": c + timedelta(hours=1),
            "label": "Лунный зенит",
        })
    except (ephem.CircumpolarError, ephem.NeverUpError, ephem.AlwaysUpError) as exc:
        logger.debug("solunar_no_upper_transit", extra={"err": str(exc)})

    # next_antitransit needs a fresh date anchor or it may return the
    # transit BEFORE the upper just found. Reset and search forward
    # from one minute after the upper transit if we have it.
    try:
        if major:
            obs.date = ephem.Date(major[-1]["end"])  # already past upper
        lower = obs.next_antitransit(moon)
        c = _to_utc(lower)
        major.append({
            "start": c - timedelta(hours=1),
            "end": c + timedelta(hours=1),
            "label": "Лунный надир",
        })
    except (ephem.CircumpolarError, ephem.NeverUpError, ephem.AlwaysUpError) as exc:
        logger.debug("solunar_no_lower_transit", extra={"err": str(exc)})

    # -- Minor: moonrise + moonset --------------------------------------
    obs.date = ephem.Date(start_dt.strftime("%Y/%m/%d %H:%M:%S"))
    try:
        rising = obs.next_rising(moon)
        c = _to_utc(rising)
        minor.append({
            "start": c - timedelta(minutes=30),
            "end": c + timedelta(minutes=30),
            "label": "Восход луны",
        })
    except (ephem.CircumpolarError, ephem.NeverUpError, ephem.AlwaysUpError) as exc:
        logger.debug("solunar_no_moonrise", extra={"err": str(exc)})

    try:
        setting = obs.next_setting(moon)
        c = _to_utc(setting)
        minor.append({
            "start": c - timedelta(minutes=30),
            "end": c + timedelta(minutes=30),
            "label": "Заход луны",
        })
    except (ephem.CircumpolarError, ephem.NeverUpError, ephem.AlwaysUpError) as exc:
        logger.debug("solunar_no_moonset", extra={"err": str(exc)})

    # -- Filter to windows whose midpoint falls within ±18h of the target
    # day's noon UTC (avoids returning events that obviously belong
    # to the next-next day).
    noon_utc = start_dt + timedelta(hours=12)
    cutoff = timedelta(hours=18)

    def in_range(window) -> bool:
        center = window["start"] + (window["end"] - window["start"]) / 2
        return abs((center - noon_utc).total_seconds()) <= cutoff.total_seconds()

    major = [w for w in major if in_range(w)]
    minor = [w for w in minor if in_range(w)]

    # -- Quality: 1 at new/full, 0 at quarters --------------------------
    illumination_pct = float(moon.phase)  # 0..100, where 100 = full
    quality = abs(illumination_pct - 50.0) / 50.0
    quality = max(0.0, min(1.0, round(quality, 2)))

    return {"major": major, "minor": minor, "quality": quality}
