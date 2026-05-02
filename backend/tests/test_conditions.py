"""Regression tests for CONDITION_REGISTRY (push notification constructor).

Each evaluator must:
 1. Match correctly given representative inputs.
 2. Return a Russian-language description for UI rendering.
 3. Honour its parameter defaults.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.push_service import CONDITION_REGISTRY, _Day, describe_conditions


def make_day(
    *,
    score=4.0,
    species="pike",
    air_temp_c=15.0,
    water_temp_c=15.0,
    wind_speed_m_s=3.0,
    cloud_cover_pct=50.0,
    precipitation_mm=0.0,
    pressure_trend_24h_hpa=0.0,
    daylight_hours=14.0,
    factor_names=frozenset(),
    on_date=None,
    moon_phase_kind=None,
    moon_growing=None,
):
    return _Day(
        date=on_date or date(2026, 7, 15),
        score=score,
        species=species,
        air_temp_c=air_temp_c,
        water_temp_c=water_temp_c,
        wind_speed_m_s=wind_speed_m_s,
        cloud_cover_pct=cloud_cover_pct,
        precipitation_mm=precipitation_mm,
        pressure_trend_24h_hpa=pressure_trend_24h_hpa,
        daylight_hours=daylight_hours,
        factor_names=set(factor_names),
        moon_phase_kind=moon_phase_kind,
        moon_growing=moon_growing,
    )


TODAY = date(2026, 4, 26)


# -- Registry coverage ------------------------------------------------------


EXPECTED_CONDITION_TYPES = {
    "score_min", "wind_max", "no_pressure_shock", "no_thermal_shock",
    "no_severe_weather", "no_precipitation", "water_temp_min",
    "water_temp_max", "pressure_stable", "cloud_max", "daylight_min",
    "lookahead_max_days", "weekend_only",
    "moon_growing", "moon_phase_in",
}


def test_registry_covers_all_expected_types():
    assert set(CONDITION_REGISTRY.keys()) == EXPECTED_CONDITION_TYPES


@pytest.mark.parametrize("type_", sorted(EXPECTED_CONDITION_TYPES))
def test_each_evaluator_describes(type_):
    evaluator = CONDITION_REGISTRY[type_]
    text = evaluator.describe({})
    assert text and isinstance(text, str)


# -- score_min --------------------------------------------------------------


def test_score_min_passes_at_or_above_threshold():
    e = CONDITION_REGISTRY["score_min"]
    assert e.matches(make_day(score=4.0), {"min": 3.5}, today=TODAY)
    assert e.matches(make_day(score=3.5), {"min": 3.5}, today=TODAY)
    assert not e.matches(make_day(score=3.4), {"min": 3.5}, today=TODAY)


def test_score_min_default_is_3_5():
    e = CONDITION_REGISTRY["score_min"]
    assert e.matches(make_day(score=3.5), {}, today=TODAY)
    assert not e.matches(make_day(score=3.0), {}, today=TODAY)


# -- wind_max ---------------------------------------------------------------


def test_wind_max_default_6_ms():
    e = CONDITION_REGISTRY["wind_max"]
    assert e.matches(make_day(wind_speed_m_s=5.0), {}, today=TODAY)
    assert e.matches(make_day(wind_speed_m_s=6.0), {}, today=TODAY)
    assert not e.matches(make_day(wind_speed_m_s=7.0), {}, today=TODAY)


def test_wind_max_custom_param():
    e = CONDITION_REGISTRY["wind_max"]
    assert e.matches(make_day(wind_speed_m_s=8.0), {"max_m_s": 10.0}, today=TODAY)
    assert not e.matches(make_day(wind_speed_m_s=11.0), {"max_m_s": 10.0}, today=TODAY)


# -- gate-presence conditions ----------------------------------------------


def test_no_pressure_shock_blocks_when_gate_active():
    e = CONDITION_REGISTRY["no_pressure_shock"]
    assert e.matches(make_day(factor_names=frozenset()), {}, today=TODAY)
    assert not e.matches(
        make_day(factor_names=frozenset(["pressure_shock_gate"])), {}, today=TODAY
    )


def test_no_thermal_shock_blocks_when_gate_active():
    e = CONDITION_REGISTRY["no_thermal_shock"]
    assert e.matches(make_day(), {}, today=TODAY)
    assert not e.matches(
        make_day(factor_names=frozenset(["thermal_shock_gate"])), {}, today=TODAY
    )


def test_no_severe_weather_blocks_when_gate_active():
    e = CONDITION_REGISTRY["no_severe_weather"]
    assert e.matches(make_day(), {}, today=TODAY)
    assert not e.matches(
        make_day(factor_names=frozenset(["severe_weather_gate"])), {}, today=TODAY
    )


# -- precipitation / temperature thresholds --------------------------------


def test_no_precipitation_default_0_5_mm():
    e = CONDITION_REGISTRY["no_precipitation"]
    assert e.matches(make_day(precipitation_mm=0.0), {}, today=TODAY)
    assert e.matches(make_day(precipitation_mm=0.5), {}, today=TODAY)
    assert not e.matches(make_day(precipitation_mm=1.0), {}, today=TODAY)


def test_water_temp_min_max_bracket():
    lo = CONDITION_REGISTRY["water_temp_min"]
    hi = CONDITION_REGISTRY["water_temp_max"]
    assert lo.matches(make_day(water_temp_c=10.0), {"min": 8.0}, today=TODAY)
    assert not lo.matches(make_day(water_temp_c=7.0), {"min": 8.0}, today=TODAY)
    assert hi.matches(make_day(water_temp_c=20.0), {"max": 24.0}, today=TODAY)
    assert not hi.matches(make_day(water_temp_c=25.0), {"max": 24.0}, today=TODAY)


def test_pressure_stable_passes_within_band():
    e = CONDITION_REGISTRY["pressure_stable"]
    assert e.matches(make_day(pressure_trend_24h_hpa=2.5), {"delta_max": 4.0}, today=TODAY)
    assert e.matches(make_day(pressure_trend_24h_hpa=-3.0), {"delta_max": 4.0}, today=TODAY)
    assert not e.matches(make_day(pressure_trend_24h_hpa=5.0), {"delta_max": 4.0}, today=TODAY)


def test_cloud_max_default_70():
    e = CONDITION_REGISTRY["cloud_max"]
    assert e.matches(make_day(cloud_cover_pct=50), {}, today=TODAY)
    assert e.matches(make_day(cloud_cover_pct=70), {}, today=TODAY)
    assert not e.matches(make_day(cloud_cover_pct=85), {}, today=TODAY)


def test_daylight_min_default_12h():
    e = CONDITION_REGISTRY["daylight_min"]
    assert e.matches(make_day(daylight_hours=15.0), {}, today=TODAY)
    assert not e.matches(make_day(daylight_hours=10.0), {}, today=TODAY)


# -- temporal: lookahead + weekend -----------------------------------------


def test_lookahead_max_days():
    e = CONDITION_REGISTRY["lookahead_max_days"]
    today = date(2026, 4, 26)
    assert e.matches(make_day(on_date=today + timedelta(days=2)), {"days": 5}, today=today)
    assert e.matches(make_day(on_date=today + timedelta(days=5)), {"days": 5}, today=today)
    assert not e.matches(make_day(on_date=today + timedelta(days=6)), {"days": 5}, today=today)


def test_weekend_only_matches_sat_sun():
    e = CONDITION_REGISTRY["weekend_only"]
    # 2026-04-25 is Saturday, 2026-04-26 is Sunday, 2026-04-27 is Monday.
    assert e.matches(make_day(on_date=date(2026, 4, 25)), {}, today=TODAY)
    assert e.matches(make_day(on_date=date(2026, 4, 26)), {}, today=TODAY)
    assert not e.matches(make_day(on_date=date(2026, 4, 27)), {}, today=TODAY)


# -- describe_conditions: human-readable summary ---------------------------


def test_describe_conditions_empty():
    assert describe_conditions([]) == "без дополнительных условий"


def test_describe_conditions_joins_with_semicolons():
    text = describe_conditions(
        [
            {"type": "score_min", "params": {"min": 3.0}},
            {"type": "weekend_only", "params": {}},
        ]
    )
    assert ";" in text
    assert "3.0" in text
    assert "выходные" in text


def test_describe_conditions_unknown_type_marked():
    text = describe_conditions([{"type": "totally_made_up", "params": {}}])
    assert "?" in text  # graceful: shows ?type instead of crashing


# -- Moon-phase conditions ---------------------------------------------


def test_moon_growing_default_matches_waxing():
    e = CONDITION_REGISTRY["moon_growing"]
    assert e.matches(make_day(moon_growing=True), {}, today=TODAY)
    assert not e.matches(make_day(moon_growing=False), {}, today=TODAY)


def test_moon_growing_inverse():
    e = CONDITION_REGISTRY["moon_growing"]
    assert e.matches(make_day(moon_growing=False), {"growing": False}, today=TODAY)
    assert not e.matches(make_day(moon_growing=True), {"growing": False}, today=TODAY)


def test_moon_phase_in_matches_listed():
    e = CONDITION_REGISTRY["moon_phase_in"]
    assert e.matches(make_day(moon_phase_kind="full"), {"kinds": ["full", "new"]}, today=TODAY)
    assert e.matches(make_day(moon_phase_kind="new"), {"kinds": ["full", "new"]}, today=TODAY)
    assert not e.matches(make_day(moon_phase_kind="first_quarter"), {"kinds": ["full", "new"]}, today=TODAY)


def test_moon_phase_in_accepts_string_param():
    """Some clients send a single value instead of a list."""
    e = CONDITION_REGISTRY["moon_phase_in"]
    assert e.matches(make_day(moon_phase_kind="full"), {"kinds": "full"}, today=TODAY)


def test_moon_phase_in_empty_list_never_matches():
    e = CONDITION_REGISTRY["moon_phase_in"]
    assert not e.matches(make_day(moon_phase_kind="full"), {"kinds": []}, today=TODAY)
