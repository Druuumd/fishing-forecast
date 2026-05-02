"""Regression tests for moon_phase decomposition."""
from __future__ import annotations

import pytest

from app.moon_phase import (
    PHASE_LABEL_RU,
    SYNODIC_PERIOD_DAYS,
    decompose,
)


def test_new_moon_at_phase_zero():
    s = decompose(0.0)
    assert s.phase_kind == "new"
    assert s.illumination_pct == 0.0
    assert s.age_days == 0.0
    assert s.growing is True


def test_full_moon_at_phase_half():
    s = decompose(0.5)
    assert s.phase_kind == "full"
    assert 99.5 <= s.illumination_pct <= 100.0
    assert abs(s.age_days - 14.77) < 0.05


def test_first_quarter_at_phase_0_25():
    s = decompose(0.25)
    assert s.phase_kind == "first_quarter"
    # Cosine formula: 0.5 * (1 - cos(π/2)) * 100 = 50%
    assert abs(s.illumination_pct - 50.0) < 0.5
    assert s.growing is True


def test_last_quarter_at_phase_0_75():
    s = decompose(0.75)
    assert s.phase_kind == "last_quarter"
    assert abs(s.illumination_pct - 50.0) < 0.5
    assert s.growing is False


def test_growing_flag_first_half():
    """Phases 0..0.5 are waxing (growing); 0.5..1 are waning."""
    for v in (0.0, 0.1, 0.25, 0.4, 0.49):
        assert decompose(v).growing is True
    for v in (0.5, 0.55, 0.75, 0.99):
        assert decompose(v).growing is False


def test_phase_kinds_cover_full_cycle():
    """Walking [0,1) should hit all 8 named phase kinds."""
    seen = set()
    for i in range(0, 1000):
        v = i / 1000.0
        seen.add(decompose(v).phase_kind)
    expected = set(PHASE_LABEL_RU) - {"new"}  # new appears at both ends
    expected.add("new")
    assert expected == seen


def test_age_days_matches_synodic_period():
    s = decompose(1.0)
    assert s.age_days == round(SYNODIC_PERIOD_DAYS, 2)


def test_label_is_russian():
    s = decompose(0.5)
    assert s.phase_label == "Полнолуние"


def test_illumination_symmetric_around_full():
    """illumination(0.4) ≈ illumination(0.6) by cosine symmetry."""
    a = decompose(0.4).illumination_pct
    b = decompose(0.6).illumination_pct
    assert abs(a - b) < 0.5


def test_phase_value_clamped_to_unit_interval():
    assert decompose(-0.1).phase_value == 0.0
    assert decompose(1.5).phase_value == 1.0
