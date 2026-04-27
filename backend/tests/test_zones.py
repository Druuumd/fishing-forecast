"""Regression tests for zone profiles and per-zone scoring effects."""
from __future__ import annotations

from datetime import date

import pytest

from app.forecast_service import _BAY_REGISTRY


ALL_BAY_CODES = (
    "syda", "ubey", "karasug", "yezagash",
    "anash", "koma",
    "ogur", "izhul", "derbino",
    "sisim", "biryusa", "tubinsky",
    "main_channel",
)


def test_all_13_bays_registered():
    assert set(_BAY_REGISTRY.keys()) == set(ALL_BAY_CODES)


def test_baseline_profile_when_no_zone(krasnoyarsk_service):
    p = krasnoyarsk_service._zone_profile(None)
    assert p["code"] is None
    assert p["water_temp_offset_c"] == 0.0
    assert p["level_sensitivity"] == 1.0
    assert p["species_base_bias"] == {}


def test_each_bay_has_required_keys(krasnoyarsk_service):
    required = {
        "code", "label", "water_temp_offset_c", "ice_freeze_temp_c",
        "ice_thaw_temp_c", "ice_months", "transition_months",
        "level_sensitivity", "species_base_bias",
    }
    for bay in ALL_BAY_CODES:
        p = krasnoyarsk_service._zone_profile(bay)
        assert required <= set(p), f"{bay} missing keys: {required - set(p)}"
        assert p["code"] == bay
        assert p["label"], f"{bay} has empty label"


def test_unknown_zone_falls_back_to_baseline(krasnoyarsk_service):
    p = krasnoyarsk_service._zone_profile("nonexistent_bay")
    assert p["code"] is None
    assert p["water_temp_offset_c"] == 0.0


def test_non_krasnoyarsk_region_returns_baseline(default_service):
    p = default_service._zone_profile("syda")
    # Bay-based zoning is Krasnoyarsk-specific; other regions get the
    # baseline regardless of what zone string is passed.
    assert p["code"] is None
    assert p["water_temp_offset_c"] == 0.0


# -- Bay differentiation: scoring ------------------------------------------


def test_shallow_bays_warmer_than_deep(krasnoyarsk_service):
    """Сыдинский (shallow_warm) should report a warmer water_temp than
    Главное русло (main_channel, deepest cold pool)."""
    syda = krasnoyarsk_service._zone_profile("syda")
    main = krasnoyarsk_service._zone_profile("main_channel")
    assert syda["water_temp_offset_c"] > main["water_temp_offset_c"]


def test_bream_bias_orders_bays(krasnoyarsk_service):
    """Bream habitat: yezagash (swampy spawning grounds) > syda > main_channel."""
    bias = lambda code: krasnoyarsk_service._zone_profile(code)["species_base_bias"]["bream"]
    assert bias("yezagash") > bias("syda") > 0.0
    assert bias("main_channel") < 0.0
    assert bias("yezagash") > bias("main_channel")


def test_level_sensitivity_higher_in_shallow_bays(krasnoyarsk_service):
    """Drawdown effect amplified in shallow bays (level_sensitivity > 1.0)
    and dampened in deep open water (< 1.0)."""
    syda = krasnoyarsk_service._zone_profile("syda")
    main = krasnoyarsk_service._zone_profile("main_channel")
    assert syda["level_sensitivity"] > 1.0
    assert main["level_sensitivity"] < 1.0


# -- Ice regime: zone-specific thresholds ----------------------------------


@pytest.mark.parametrize("bay", ALL_BAY_CODES)
def test_ice_freeze_threshold_within_realistic_range(krasnoyarsk_service, bay):
    p = krasnoyarsk_service._zone_profile(bay)
    # Eastern Siberia reservoirs freeze when surface water cools to ~0-2°C.
    assert 0.0 < p["ice_freeze_temp_c"] <= 2.0


def test_main_channel_ice_window_shorter_than_shallow_bays(krasnoyarsk_service):
    """Deep main channel: ice forms later (Dec) and breaks earlier;
    shallow Сыдинский залив: ice extends Nov–May."""
    syda = krasnoyarsk_service._zone_profile("syda")
    main = krasnoyarsk_service._zone_profile("main_channel")
    assert len(syda["ice_months"]) > len(main["ice_months"])


# -- water_temp_offset doubles via zone-aware scoring -----------------------


def test_zone_offset_applied_to_water_temp_in_scoring(krasnoyarsk_service, make_snapshot_fixture):
    """When apply_zone_temp_offset=True (default), scoring sees Tw shifted
    by the zone's offset. So a Tw=18°C snapshot scored against syda
    (offset +1.5) should treat water as 19.5°C — a difference visible in
    the water_temp factor's detail string."""
    snap = make_snapshot_fixture(water_temp_c=18.0)
    syda_profile = krasnoyarsk_service._zone_profile("syda")
    _, _, factors = krasnoyarsk_service._score_with_factors("bream", snap, zone=syda_profile)
    wt = next(f for f in factors if f.name == "water_temp")
    assert "19.5" in wt.detail or "19.4" in wt.detail
