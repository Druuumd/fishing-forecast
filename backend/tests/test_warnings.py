"""Regression tests for the warnings service rules."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from app.warnings_service import compute_warnings


@dataclass
class _Factor:
    name: str
    detail: str = ""


@dataclass
class _Day:
    date: date
    score: float = 3.0
    species: str = "pike"
    air_temp_c: float = 12.0
    water_temp_c: float = 10.0
    wind_speed_m_s: float = 4.0
    wind_direction_deg: float = 200.0
    cloud_cover_pct: float = 50.0
    precipitation_mm: float = 0.0
    pressure_trend_24h_hpa: float = 0.0
    daylight_hours: float = 14.0
    factors: list = None

    def __post_init__(self):
        if self.factors is None:
            self.factors = []


@dataclass
class _WaterLevelState:
    latest_level_m: float = 235.0
    latest_day: date = date(2026, 6, 1)
    trend_7d_m: float = 0.0
    source: str = "manual"
    is_fresh: bool = True


def codes(warnings):
    return {w.code for w in warnings}


# Pick a date OUTSIDE the spawning ban window so we don't have to filter
# it out of every test. 1 July is well past 10 June.
SAFE_DAY = date(2026, 7, 1)


# -- Pressure shock ----------------------------------------------------


def test_pressure_shock_warning_fires_when_gate_present():
    days = [_Day(SAFE_DAY, factors=[_Factor("pressure_shock_gate", "ΔP24h=+8.0 hPa")])]
    out = compute_warnings(today=SAFE_DAY, forecast_days=days)
    assert "pressure_shock" in codes(out)


def test_pressure_shock_warning_skips_clean_days():
    days = [_Day(SAFE_DAY, factors=[_Factor("water_temp")])]
    out = compute_warnings(today=SAFE_DAY, forecast_days=days)
    assert "pressure_shock" not in codes(out)


def test_pressure_shock_only_inspects_lookahead_window():
    """Gate active on day-5 should not fire when lookahead=3."""
    days = [_Day(date(2026, 7, 1)), _Day(date(2026, 7, 2)), _Day(date(2026, 7, 3))]
    days.append(_Day(date(2026, 7, 4), factors=[_Factor("pressure_shock_gate")]))
    days.append(_Day(date(2026, 7, 5), factors=[_Factor("pressure_shock_gate")]))
    out = compute_warnings(today=SAFE_DAY, forecast_days=days, lookahead_days=3)
    assert "pressure_shock" not in codes(out)


# -- Severe weather ----------------------------------------------------


def test_severe_weather_warning_marks_danger():
    days = [_Day(SAFE_DAY, factors=[_Factor("severe_weather_gate")])]
    out = compute_warnings(today=SAFE_DAY, forecast_days=days)
    sw = next(w for w in out if w.code == "severe_weather")
    assert sw.severity == "danger"


# -- Gale wind ---------------------------------------------------------


def test_gale_wind_warning_at_12_ms():
    days = [_Day(SAFE_DAY, wind_speed_m_s=12.5)]
    out = compute_warnings(today=SAFE_DAY, forecast_days=days)
    assert "gale_wind" in codes(out)


def test_no_gale_warning_when_breezy():
    days = [_Day(SAFE_DAY, wind_speed_m_s=8.0)]
    out = compute_warnings(today=SAFE_DAY, forecast_days=days)
    assert "gale_wind" not in codes(out)


# -- Heavy rain --------------------------------------------------------


def test_heavy_rain_at_8_mm_threshold():
    days = [_Day(SAFE_DAY, precipitation_mm=8.5)]
    out = compute_warnings(today=SAFE_DAY, forecast_days=days)
    assert "heavy_rain" in codes(out)


# -- Ice unsafe (transition) ------------------------------------------


def test_ice_unsafe_when_transition_active():
    days = [_Day(SAFE_DAY, factors=[_Factor("ice_regime", "transition (Tw=2.7°C)")])]
    out = compute_warnings(today=SAFE_DAY, forecast_days=days)
    ice = next(w for w in out if w.code == "ice_unsafe")
    assert ice.severity == "danger"


def test_ice_open_no_warning():
    days = [_Day(SAFE_DAY, factors=[_Factor("ice_regime", "open (Tw=12.0°C)")])]
    out = compute_warnings(today=SAFE_DAY, forecast_days=days)
    assert "ice_unsafe" not in codes(out)


# -- Drawdown ---------------------------------------------------------


def test_drawdown_warning_at_minus_1m_per_week():
    state = _WaterLevelState(trend_7d_m=-1.2)
    out = compute_warnings(today=SAFE_DAY, forecast_days=[], water_level_state=state)
    assert "drawdown_alarm" in codes(out)


def test_no_drawdown_for_normal_seasonal_drop():
    state = _WaterLevelState(trend_7d_m=-0.4)
    out = compute_warnings(today=SAFE_DAY, forecast_days=[], water_level_state=state)
    assert "drawdown_alarm" not in codes(out)


# -- Spawning ban ------------------------------------------------------


def test_spawning_ban_active_in_may():
    out = compute_warnings(today=date(2026, 5, 15), forecast_days=[])
    sb = next(w for w in out if w.code == "spawning_ban")
    assert sb.severity == "info"


def test_spawning_ban_inactive_in_winter():
    out = compute_warnings(today=date(2026, 1, 15), forecast_days=[])
    assert "spawning_ban" not in codes(out)


def test_spawning_ban_default_window_25apr_25jun_inclusive():
    """Per приказ Минсельхоза №226: 25.04 – 25.06 inclusive."""
    out_start = compute_warnings(today=date(2026, 4, 25), forecast_days=[])
    out_mid = compute_warnings(today=date(2026, 5, 30), forecast_days=[])
    out_end = compute_warnings(today=date(2026, 6, 25), forecast_days=[])
    assert "spawning_ban" in codes(out_start)
    assert "spawning_ban" in codes(out_mid)
    assert "spawning_ban" in codes(out_end)


def test_spawning_ban_window_excludes_day_before_and_after():
    out_before = compute_warnings(today=date(2026, 4, 24), forecast_days=[])
    out_after = compute_warnings(today=date(2026, 6, 26), forecast_days=[])
    assert "spawning_ban" not in codes(out_before)
    assert "spawning_ban" not in codes(out_after)


def test_spawning_ban_window_overridable_via_env_args():
    """Operator can override dates without code change."""
    out = compute_warnings(
        today=date(2026, 7, 5), forecast_days=[],
        spawning_ban_start_md="07-01", spawning_ban_end_md="07-15",
    )
    assert "spawning_ban" in codes(out)


def test_spawning_ban_body_mentions_legal_basis():
    out = compute_warnings(today=date(2026, 5, 15), forecast_days=[])
    sb = next(w for w in out if w.code == "spawning_ban")
    # Должны упомянуть: водохранилище, приказ, разрешённое орудие.
    assert "водохранилище" in sb.body.lower()
    assert "минсельхоз" in sb.body.lower() or "правил" in sb.body.lower()
    assert "удочк" in sb.body.lower()


# -- Multiple stack -----------------------------------------------------


def test_stacked_warnings_all_emitted():
    """Several rules trip on the same day — each one should produce its own item."""
    days = [_Day(
        SAFE_DAY,
        wind_speed_m_s=14.0, precipitation_mm=15.0,
        factors=[_Factor("pressure_shock_gate"), _Factor("severe_weather_gate")],
    )]
    out = compute_warnings(today=SAFE_DAY, forecast_days=days)
    cs = codes(out)
    for c in ("pressure_shock", "severe_weather", "gale_wind", "heavy_rain"):
        assert c in cs, f"missing {c} in {cs}"
