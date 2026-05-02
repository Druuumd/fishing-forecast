"""Validation + zone-detection tests for user-submitted water-temp readings."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.water_temp_readings import detect_zone, validate_reading


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)


def _ok_kwargs(**overrides):
    base = dict(
        measured_at=NOW - timedelta(hours=1),
        latitude=55.30,
        longitude=91.70,
        surface_temp_c=20.0,
        thermocline_depth_m=8.0,
        below_thermocline_temp_c=6.0,
    )
    base.update(overrides)
    return base


# -- Happy path --------------------------------------------------------


def test_valid_reading_passes():
    r = validate_reading(now=NOW, **_ok_kwargs())
    assert r.valid
    assert r.errors == {}


def test_surface_only_no_thermocline_passes():
    """User without sonar can submit just surface temp."""
    r = validate_reading(now=NOW, **_ok_kwargs(
        thermocline_depth_m=None, below_thermocline_temp_c=None,
    ))
    assert r.valid


# -- Time validation ---------------------------------------------------


def test_future_timestamp_rejected():
    r = validate_reading(now=NOW, **_ok_kwargs(measured_at=NOW + timedelta(hours=2)))
    assert not r.valid
    assert "measured_at" in r.errors


def test_old_reading_rejected():
    r = validate_reading(now=NOW, **_ok_kwargs(measured_at=NOW - timedelta(days=45)))
    assert not r.valid
    assert "measured_at" in r.errors


# -- GPS bbox ----------------------------------------------------------


def test_lat_outside_bbox_rejected():
    r = validate_reading(now=NOW, **_ok_kwargs(latitude=60.0))  # too far north
    assert not r.valid
    assert "latitude" in r.errors


def test_lon_outside_bbox_rejected():
    r = validate_reading(now=NOW, **_ok_kwargs(longitude=80.0))  # outside
    assert not r.valid
    assert "longitude" in r.errors


# -- Temperature ranges ------------------------------------------------


def test_surface_temp_too_high_rejected():
    r = validate_reading(now=NOW, **_ok_kwargs(surface_temp_c=35.0))
    assert not r.valid
    assert "surface_temp_c" in r.errors


def test_below_temp_above_surface_rejected():
    """Physically impossible: thermocline cools the water."""
    r = validate_reading(now=NOW, **_ok_kwargs(
        surface_temp_c=10.0, below_thermocline_temp_c=15.0,
    ))
    assert not r.valid
    assert "below_thermocline_temp_c" in r.errors


def test_below_temp_outside_range_rejected():
    r = validate_reading(now=NOW, **_ok_kwargs(below_thermocline_temp_c=-1.0))
    assert not r.valid
    assert "below_thermocline_temp_c" in r.errors


def test_thermocline_depth_outside_range_rejected():
    r = validate_reading(now=NOW, **_ok_kwargs(thermocline_depth_m=80.0))
    assert not r.valid
    assert "thermocline_depth_m" in r.errors


# -- Partial profile -------------------------------------------------


def test_depth_without_below_temp_rejected():
    r = validate_reading(now=NOW, **_ok_kwargs(below_thermocline_temp_c=None))
    assert not r.valid
    assert "below_thermocline_temp_c" in r.errors


def test_below_temp_without_depth_rejected():
    r = validate_reading(now=NOW, **_ok_kwargs(thermocline_depth_m=None))
    assert not r.valid
    assert "thermocline_depth_m" in r.errors


# -- Zone detection -----------------------------------------------------


def test_detect_zone_inside_bay():
    """Coordinates near Сыдинский залив (~54.55, 91.50) → 'syda'."""
    z = detect_zone(54.55, 91.50)
    assert z == "syda"


def test_detect_zone_open_water_near_main_channel_center():
    """Point near main_channel coordinates routes to main_channel."""
    z = detect_zone(55.00, 91.70)
    assert z == "main_channel"


def test_detect_zone_far_from_any_bay_still_returns_main_channel():
    """Point in the bbox but >25 km from every bay center falls back
    to 'main_channel' as the generic open-water bucket."""
    # Northern slice of bbox, far west of all bay centers.
    z = detect_zone(55.95, 90.7)
    assert z == "main_channel"


def test_detect_zone_outside_bbox_returns_none():
    z = detect_zone(60.0, 80.0)
    assert z is None


def test_detect_zone_for_each_named_bay():
    """All 13 bay codes are reachable for points near their centers."""
    from app.weather_ingest import BAY_CENTERS
    for code, (lat, lon) in BAY_CENTERS.items():
        # A point exactly at the bay center should map to that code
        # (tibreaker by minimum distance, distance=0 wins).
        z = detect_zone(lat, lon)
        assert z == code, f"{code} center not detected (got {z})"
