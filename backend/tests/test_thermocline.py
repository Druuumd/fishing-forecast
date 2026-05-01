"""Regression tests for thermocline_advisory."""
from __future__ import annotations

import pytest


def test_baseline_zone_returns_neutral(default_service):
    """Non-Krasnoyarsk region — no advisory."""
    result = default_service.thermocline_advisory(water_temp_c=22.0, zone=None)
    assert result["strength"] == 0.0
    assert result["depth_m"] is None


def test_no_zone_returns_neutral(krasnoyarsk_service):
    result = krasnoyarsk_service.thermocline_advisory(water_temp_c=22.0, zone=None)
    assert result["strength"] == 0.0


def test_cold_water_no_stratification(krasnoyarsk_service):
    """Below 12°C — water column mixed, no thermocline."""
    profile = krasnoyarsk_service._zone_profile("main_channel")
    r = krasnoyarsk_service.thermocline_advisory(water_temp_c=8.0, zone=profile)
    assert r["strength"] == 0.0
    assert r["depth_m"] is None


def test_warm_water_in_deep_channel_strong_stratification(krasnoyarsk_service):
    """22°C surface in main channel — should report a sharp thermocline."""
    profile = krasnoyarsk_service._zone_profile("main_channel")
    r = krasnoyarsk_service.thermocline_advisory(water_temp_c=22.0, zone=profile)
    assert r["strength"] >= 0.95
    assert r["depth_m"] is not None
    assert 12 <= r["depth_m"] <= 20
    assert r["recommended_depth_m"] is not None
    assert r["recommended_depth_m"] < r["depth_m"]
    assert "термоклин" in r["advice"].lower()


def test_warm_water_in_shallow_bay_weak_stratification(krasnoyarsk_service):
    """22°C in Сыдинский залив — capacity is low, expect weak stratification."""
    profile = krasnoyarsk_service._zone_profile("syda")
    r = krasnoyarsk_service.thermocline_advisory(water_temp_c=22.0, zone=profile)
    # syda has strat_capacity 0.3 → strength should be ≤ 0.30.
    assert r["strength"] <= 0.30


def test_swampy_shallow_almost_never_stratifies(krasnoyarsk_service):
    """Езагашский залив — заболоченный, мелкий — практически никогда не
    держит термоклин даже в жару."""
    profile = krasnoyarsk_service._zone_profile("yezagash")
    r = krasnoyarsk_service.thermocline_advisory(water_temp_c=23.0, zone=profile)
    assert r["strength"] <= 0.20


def test_advice_text_present_for_strong_thermocline(krasnoyarsk_service):
    profile = krasnoyarsk_service._zone_profile("biryusa")
    r = krasnoyarsk_service.thermocline_advisory(water_temp_c=22.0, zone=profile)
    assert r["advice"]
    assert any(kw in r["advice"].lower() for kw in ("термоклин", "троллинг", "глубин", "м"))


def test_recommended_depth_above_thermocline(krasnoyarsk_service):
    """Bait should sit ≥1 m above the cliff, not at it."""
    for archetype in ("medium_balanced", "steep_cool", "deep_cold", "main_channel"):
        for code in [c for c, _ in [("ogur", 1), ("sisim", 1), ("tubinsky", 1), ("main_channel", 1)]
                     if archetype != "deep_cold" or c == "tubinsky"]:
            pass
    # Same logic, but checked once via the deepest channel:
    profile = krasnoyarsk_service._zone_profile("main_channel")
    r = krasnoyarsk_service.thermocline_advisory(water_temp_c=22.0, zone=profile)
    assert r["recommended_depth_m"] <= r["depth_m"] - 1


def test_advisory_grows_with_temperature(krasnoyarsk_service):
    profile = krasnoyarsk_service._zone_profile("derbino")
    cold = krasnoyarsk_service.thermocline_advisory(water_temp_c=14.0, zone=profile)
    warm = krasnoyarsk_service.thermocline_advisory(water_temp_c=20.0, zone=profile)
    assert warm["strength"] > cold["strength"]


def test_recent_wind_does_not_affect_quiet_days(krasnoyarsk_service):
    """Light winds (< 8 m/s) leave the thermocline alone."""
    profile = krasnoyarsk_service._zone_profile("biryusa")
    quiet = krasnoyarsk_service.thermocline_advisory(
        water_temp_c=22.0, zone=profile,
        recent_wind_speeds_m_s=[3.0, 4.0, 5.0],
    )
    none_winds = krasnoyarsk_service.thermocline_advisory(
        water_temp_c=22.0, zone=profile,
    )
    assert quiet["strength"] == none_winds["strength"]


def test_sustained_gale_breaks_thermocline(krasnoyarsk_service):
    """Three-day average ≥8 m/s halves the thermocline strength."""
    profile = krasnoyarsk_service._zone_profile("biryusa")
    calm = krasnoyarsk_service.thermocline_advisory(
        water_temp_c=22.0, zone=profile,
    )
    blown = krasnoyarsk_service.thermocline_advisory(
        water_temp_c=22.0, zone=profile,
        recent_wind_speeds_m_s=[10.0, 10.0, 10.0],
    )
    assert blown["strength"] < calm["strength"] * 0.6


def test_extreme_gale_almost_eliminates_thermocline(krasnoyarsk_service):
    """At 12+ m/s sustained the column is mostly mixed."""
    profile = krasnoyarsk_service._zone_profile("main_channel")
    blown = krasnoyarsk_service.thermocline_advisory(
        water_temp_c=22.0, zone=profile,
        recent_wind_speeds_m_s=[14.0, 13.0, 15.0],
    )
    # 1.0 capacity × 1.0 temp × 0.2 wind_mix = 0.2
    assert blown["strength"] <= 0.25


def test_zone_archetype_exposed_in_profile(krasnoyarsk_service):
    """The advisory needs the archetype, so the profile must expose it."""
    for code in ("syda", "main_channel", "tubinsky"):
        p = krasnoyarsk_service._zone_profile(code)
        assert "archetype" in p, code
        assert p["archetype"], code
