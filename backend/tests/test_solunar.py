"""Regression tests for solunar.compute_solunar_periods.

Verify structure + invariants. Exact times are computed by PyEphem
which we trust; we sanity-check that windows fall in the expected
ranges (e.g. ~24h apart for transits, lunar quality high near full
moon, etc.).
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.solunar import compute_solunar_periods


KRSK_LAT, KRSK_LON = 55.0, 91.7


# -- Structure --------------------------------------------------------


def test_returns_required_keys():
    out = compute_solunar_periods(
        target_date=date(2026, 7, 15), lat=KRSK_LAT, lon=KRSK_LON
    )
    assert set(out.keys()) == {"major", "minor", "quality"}


def test_each_window_has_start_end_label():
    out = compute_solunar_periods(
        target_date=date(2026, 7, 15), lat=KRSK_LAT, lon=KRSK_LON
    )
    for w in out["major"] + out["minor"]:
        assert {"start", "end", "label"} <= set(w)


def test_major_window_is_2h_wide():
    out = compute_solunar_periods(
        target_date=date(2026, 7, 15), lat=KRSK_LAT, lon=KRSK_LON
    )
    for w in out["major"]:
        assert w["end"] - w["start"] == timedelta(hours=2)


def test_minor_window_is_1h_wide():
    out = compute_solunar_periods(
        target_date=date(2026, 7, 15), lat=KRSK_LAT, lon=KRSK_LON
    )
    for w in out["minor"]:
        assert w["end"] - w["start"] == timedelta(hours=1)


def test_at_most_two_major_at_most_two_minor():
    """A given target day produces at most one upper transit + one
    anti-transit + one moonrise + one moonset within the ±18h cutoff."""
    out = compute_solunar_periods(
        target_date=date(2026, 7, 15), lat=KRSK_LAT, lon=KRSK_LON
    )
    assert 0 < len(out["major"]) <= 2
    assert 0 < len(out["minor"]) <= 2


def test_quality_in_unit_interval():
    out = compute_solunar_periods(
        target_date=date(2026, 7, 15), lat=KRSK_LAT, lon=KRSK_LON
    )
    assert 0.0 <= out["quality"] <= 1.0


def test_all_returned_times_are_utc():
    out = compute_solunar_periods(
        target_date=date(2026, 7, 15), lat=KRSK_LAT, lon=KRSK_LON
    )
    for w in out["major"] + out["minor"]:
        assert w["start"].tzinfo is not None
        assert w["end"].tzinfo is not None


# -- Quality at known phases -----------------------------------------


def test_quality_high_near_full_moon():
    """May 1, 2026 is a full moon (per published lunar calendar).
    Quality should be high (illumination near 100%)."""
    out = compute_solunar_periods(
        target_date=date(2026, 5, 1), lat=KRSK_LAT, lon=KRSK_LON
    )
    assert out["quality"] >= 0.9


def test_quality_low_near_quarter():
    """A first-quarter date should have low quality (illumination ~50%)."""
    # Approximate first quarter: April 24, 2026 (between new on Apr 17
    # and full on May 1).
    out = compute_solunar_periods(
        target_date=date(2026, 4, 24), lat=KRSK_LAT, lon=KRSK_LON
    )
    assert out["quality"] <= 0.3


# -- Sane chronology --------------------------------------------------


def test_transits_roughly_12h_apart():
    """Upper and lower transits of the moon are separated by ~12h25min."""
    out = compute_solunar_periods(
        target_date=date(2026, 7, 15), lat=KRSK_LAT, lon=KRSK_LON
    )
    if len(out["major"]) < 2:
        pytest.skip("only one transit fell in the cutoff window")
    centers = sorted(
        w["start"] + (w["end"] - w["start"]) / 2 for w in out["major"]
    )
    delta = centers[1] - centers[0]
    # 12h25min ± 30min slack.
    assert timedelta(hours=11, minutes=55) <= delta <= timedelta(hours=12, minutes=55)


def test_event_centers_within_18h_of_noon():
    """The cutoff filter rejects events too far from the target day's noon."""
    target = date(2026, 7, 15)
    noon = datetime(target.year, target.month, target.day, 12, 0, tzinfo=UTC)
    out = compute_solunar_periods(target_date=target, lat=KRSK_LAT, lon=KRSK_LON)
    for w in out["major"] + out["minor"]:
        center = w["start"] + (w["end"] - w["start"]) / 2
        assert abs((center - noon).total_seconds()) <= 18 * 3600


# -- Geographic dependence -------------------------------------------


def test_different_longitudes_shift_event_times():
    """Moonrise at Krasnoyarsk (91°E) and Vladivostok (132°E) on the
    same UTC date should be ~2.7h apart (since each 15° of longitude
    shifts local moonrise time by an hour, and Vladivostok is 41°
    east of Krasnoyarsk)."""
    krsk = compute_solunar_periods(
        target_date=date(2026, 7, 15), lat=55.0, lon=91.0
    )
    vlad = compute_solunar_periods(
        target_date=date(2026, 7, 15), lat=43.0, lon=132.0
    )
    if not krsk["minor"] or not vlad["minor"]:
        pytest.skip("no rise/set fell within cutoff for one location")
    krsk_rise = next(w for w in krsk["minor"] if "Восход" in w["label"])
    vlad_rise = next(w for w in vlad["minor"] if "Восход" in w["label"])
    delta = abs((krsk_rise["start"] - vlad_rise["start"]).total_seconds()) / 3600.0
    assert 2.0 <= delta <= 3.5
