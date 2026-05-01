"""Shared fixtures for the backend test suite.

The scoring layer is pure: ForecastService doesn't touch the DB or
network, so we can instantiate it directly with a stub repository.
"""
from __future__ import annotations

from datetime import date, datetime, UTC

import pytest

from app.forecast_service import ForecastService, WaterLevelContext, WeatherSnapshot


class _StubCatchRepository:
    """No-op stand-in for CatchRepository — scoring never touches it."""

    def save(self, *_args, **_kwargs):  # pragma: no cover
        raise AssertionError("scoring should not touch the catch repository")


@pytest.fixture()
def krasnoyarsk_service() -> ForecastService:
    return ForecastService(
        catch_repository=_StubCatchRepository(),
        region="krasnoyarsk",
        region_elevation_m=234.0,
    )


@pytest.fixture()
def default_service() -> ForecastService:
    return ForecastService(
        catch_repository=_StubCatchRepository(),
        region="default",
    )


def make_snapshot(
    *,
    day: date = date(2026, 7, 15),
    air_temp_c: float = 22.0,
    pressure_hpa: float = 1013.0,
    water_temp_c: float = 18.0,
    wind_speed_m_s: float = 3.0,
    wind_direction_deg: float = 200.0,
    moon_phase: float = 0.5,
    cloud_cover_pct: float = 50.0,
    precipitation_mm: float = 0.0,
    humidity_pct: float = 65.0,
    pressure_trend_6h_hpa: float = 0.0,
    pressure_trend_24h_hpa: float = 0.0,
    daylight_hours: float = 16.0,
    sunrise=None,
    sunset=None,
) -> WeatherSnapshot:
    """Concise factory for test snapshots — explicit kwargs for clarity."""
    return WeatherSnapshot(
        day=day,
        air_temp_c=air_temp_c,
        pressure_hpa=pressure_hpa,
        water_temp_c=water_temp_c,
        wind_speed_m_s=wind_speed_m_s,
        wind_direction_deg=wind_direction_deg,
        moon_phase=moon_phase,
        cloud_cover_pct=cloud_cover_pct,
        precipitation_mm=precipitation_mm,
        humidity_pct=humidity_pct,
        pressure_trend_6h_hpa=pressure_trend_6h_hpa,
        pressure_trend_24h_hpa=pressure_trend_24h_hpa,
        daylight_hours=daylight_hours,
        sunrise=sunrise,
        sunset=sunset,
    )


@pytest.fixture()
def make_snapshot_fixture():
    return make_snapshot


@pytest.fixture()
def calm_water_level() -> WaterLevelContext:
    return WaterLevelContext(
        latest_level_m=240.0,
        trend_7d_m=0.0,
        source="manual",
        is_fresh=True,
    )
