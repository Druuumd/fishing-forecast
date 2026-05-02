"""Regression tests for the core scoring pipeline.

The scoring is an additive sum of factors clamped to [0, 5], with
multiplicative gates applied on top for sharp non-linear conditions
(pressure shock, severe weather, thermal shock).
"""
from __future__ import annotations

from datetime import date

import pytest


def names(factors):
    return {f.name for f in factors}


def factor(factors, name):
    for f in factors:
        if f.name == name:
            return f
    return None


# -- _score_with_factors: shape and contract --------------------------------


def test_score_within_bounds(krasnoyarsk_service, make_snapshot_fixture):
    snap = make_snapshot_fixture()
    for species in ("pike", "perch", "bream"):
        score, conf, factors = krasnoyarsk_service._score_with_factors(species, snap)
        assert 0.0 <= score <= 5.0
        assert 0.0 <= conf <= 1.0
        assert factors, "factor list must never be empty"


def test_factor_list_contains_base_water_temp_pressure(krasnoyarsk_service, make_snapshot_fixture):
    snap = make_snapshot_fixture()
    _, _, factors = krasnoyarsk_service._score_with_factors("bream", snap)
    fnames = names(factors)
    assert "base" in fnames
    assert "water_temp" in fnames
    assert "pressure" in fnames
    assert "season" in fnames


def test_pressure_factor_uses_surface_pressure(krasnoyarsk_service, make_snapshot_fixture):
    snap = make_snapshot_fixture(pressure_hpa=1015.0, air_temp_c=10.0)
    _, _, factors = krasnoyarsk_service._score_with_factors("pike", snap)
    p = factor(factors, "pressure")
    # Detail line should expose both MSL and converted surface pressure.
    assert "MSL" in p.detail
    assert "surface" in p.detail
    # At elevation 234 m, surface pressure is ~27-29 hPa below MSL.
    assert "988" in p.detail or "987" in p.detail or "986" in p.detail


# -- Multiplicative gates: pressure shock -----------------------------------


def test_pressure_shock_gate_inactive_below_threshold(krasnoyarsk_service, make_snapshot_fixture):
    snap = make_snapshot_fixture(pressure_trend_24h_hpa=2.0)
    _, _, factors = krasnoyarsk_service._score_with_factors("perch", snap)
    assert "pressure_shock_gate" not in names(factors)


def test_pressure_shock_gate_active_at_8_hpa(krasnoyarsk_service, make_snapshot_fixture):
    """ΔP24h=+8 hPa is a notable shock — gate must fire for all species."""
    snap = make_snapshot_fixture(pressure_trend_24h_hpa=8.0)
    for species in ("pike", "perch", "bream"):
        _, _, factors = krasnoyarsk_service._score_with_factors(species, snap)
        assert "pressure_shock_gate" in names(factors), species


def test_pressure_shock_gate_severity_orders_species(krasnoyarsk_service, make_snapshot_fixture):
    """Bream is most sensitive, pike least. With identical conditions and
    a ΔP24h=10 hPa shock, the gate multiplier should follow:
    pike > perch > bream (less reduction = larger multiplier)."""
    snap = make_snapshot_fixture(pressure_trend_24h_hpa=10.0)
    pike = krasnoyarsk_service._pressure_shock_gate(10.0, species="pike")
    perch = krasnoyarsk_service._pressure_shock_gate(10.0, species="perch")
    bream = krasnoyarsk_service._pressure_shock_gate(10.0, species="bream")
    assert pike > perch > bream
    assert 0.30 <= bream <= 1.0


def test_pressure_shock_gate_floor_at_extreme(krasnoyarsk_service):
    """At ≥12 hPa the gate hits its species-specific floor."""
    assert krasnoyarsk_service._pressure_shock_gate(15.0, species="bream") == pytest.approx(0.30)
    assert krasnoyarsk_service._pressure_shock_gate(15.0, species="pike") == pytest.approx(0.45)
    assert krasnoyarsk_service._pressure_shock_gate(-15.0, species="bream") == pytest.approx(0.30)


# -- Multiplicative gates: severe weather -----------------------------------


def test_severe_weather_gate_inactive_in_calm(krasnoyarsk_service, make_snapshot_fixture):
    snap = make_snapshot_fixture(wind_speed_m_s=4.0, precipitation_mm=2.0)
    assert krasnoyarsk_service._severe_weather_gate(snap) == 1.0


def test_severe_weather_gate_active_in_storm(krasnoyarsk_service, make_snapshot_fixture):
    snap = make_snapshot_fixture(wind_speed_m_s=15.0, precipitation_mm=18.0)
    gate = krasnoyarsk_service._severe_weather_gate(snap)
    assert gate <= 0.45


# -- Multiplicative gates: thermal shock -----------------------------------


def test_thermal_shock_bream_below_feeding_threshold(krasnoyarsk_service):
    """Bream stops feeding below ~8°C; below 4°C it hits the floor."""
    assert krasnoyarsk_service._thermal_shock_gate(10.0, species="bream") == 1.0
    assert krasnoyarsk_service._thermal_shock_gate(4.0, species="bream") == 0.35
    assert krasnoyarsk_service._thermal_shock_gate(2.0, species="bream") == 0.35
    # Mid-range is interpolated.
    mid = krasnoyarsk_service._thermal_shock_gate(6.0, species="bream")
    assert 0.35 < mid < 1.0


def test_thermal_shock_pike_lockjaw_under_2c(krasnoyarsk_service):
    assert krasnoyarsk_service._thermal_shock_gate(3.0, species="pike") == 1.0
    assert krasnoyarsk_service._thermal_shock_gate(0.0, species="pike") == 0.55
    assert krasnoyarsk_service._thermal_shock_gate(1.0, species="pike") == pytest.approx(0.775)


def test_thermal_shock_perch_only_extreme_heat(krasnoyarsk_service):
    """Perch is broadly tolerant; only extreme heat dampens."""
    assert krasnoyarsk_service._thermal_shock_gate(10.0, species="perch") == 1.0
    assert krasnoyarsk_service._thermal_shock_gate(20.0, species="perch") == 1.0
    assert krasnoyarsk_service._thermal_shock_gate(25.0, species="perch") == 0.8
    assert krasnoyarsk_service._thermal_shock_gate(27.0, species="perch") == 0.6


# -- Compound: gates compose multiplicatively -------------------------------


def test_two_gates_compose_below_either_alone(krasnoyarsk_service, make_snapshot_fixture):
    """A bream day with both pressure shock and thermal shock should land
    lower than a day with either alone."""
    base = make_snapshot_fixture(water_temp_c=18.0, pressure_trend_24h_hpa=0.0)
    only_pressure = make_snapshot_fixture(water_temp_c=18.0, pressure_trend_24h_hpa=10.0)
    only_thermal = make_snapshot_fixture(water_temp_c=4.0, pressure_trend_24h_hpa=0.0)
    both = make_snapshot_fixture(water_temp_c=4.0, pressure_trend_24h_hpa=10.0)

    s_base, _, _ = krasnoyarsk_service._score_with_factors("bream", base)
    s_p, _, _ = krasnoyarsk_service._score_with_factors("bream", only_pressure)
    s_t, _, _ = krasnoyarsk_service._score_with_factors("bream", only_thermal)
    s_both, _, _ = krasnoyarsk_service._score_with_factors("bream", both)

    assert s_both <= s_p
    assert s_both <= s_t
    assert s_base > s_both


def test_confidence_drops_with_gates(krasnoyarsk_service, make_snapshot_fixture):
    calm = make_snapshot_fixture(pressure_trend_24h_hpa=0.0)
    shock = make_snapshot_fixture(pressure_trend_24h_hpa=10.0)
    _, c_calm, _ = krasnoyarsk_service._score_with_factors("perch", calm)
    _, c_shock, _ = krasnoyarsk_service._score_with_factors("perch", shock)
    assert c_shock < c_calm


# -- Surface pressure (barometric formula) ----------------------------------


def test_surface_pressure_at_zero_elevation_is_msl():
    from app.forecast_service import ForecastService

    sea_level = ForecastService(
        catch_repository=None,  # type: ignore[arg-type]
        region="default",
        region_elevation_m=0.0,
    )
    assert sea_level._surface_pressure_hpa(15.0, 1013.25) == 1013.25


def test_surface_pressure_at_234m_is_about_27_hpa_below(krasnoyarsk_service):
    surf = krasnoyarsk_service._surface_pressure_hpa(15.0, 1013.25)
    delta = 1013.25 - surf
    # ICAO standard atmosphere predicts ~28 hPa drop at 234 m for typical T.
    assert 25.0 < delta < 31.0


def test_surface_pressure_colder_air_increases_delta(krasnoyarsk_service):
    """Cold air is denser → larger MSL→surface drop."""
    summer = 1013.25 - krasnoyarsk_service._surface_pressure_hpa(25.0, 1013.25)
    winter = 1013.25 - krasnoyarsk_service._surface_pressure_hpa(-25.0, 1013.25)
    assert winter > summer
