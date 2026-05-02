"""Regression tests for species-specific spawning state."""
from __future__ import annotations

from datetime import date

import pytest

from app.species_spawning import (
    SPECIES_SPAWN_PROFILES,
    species_spawn_factor_contribution,
    species_spawn_state,
)


# -- Outside calendar window --------------------------------------------


def test_winter_no_spawn_for_any_species():
    for sp in ("pike", "perch", "bream"):
        s = species_spawn_state(sp, date(2026, 1, 15), water_temp_c=2.0)
        assert s.phase == "none"


def test_summer_after_post_temp_no_spawn():
    """At Tw 22°C in July all three species are well past their windows."""
    for sp in ("pike", "perch", "bream"):
        s = species_spawn_state(sp, date(2026, 7, 15), water_temp_c=22.0)
        # Calendar months are 4-5 (pike/perch) or 5-6 (bream); July is out
        # for everyone.
        assert s.phase == "none", sp


def test_unknown_species_returns_none():
    s = species_spawn_state("salmon", date(2026, 5, 15), water_temp_c=10.0)
    assert s.phase == "none"


# -- Pike phases --------------------------------------------------------


def test_pike_pre_spawn_at_3c_late_april():
    s = species_spawn_state("pike", date(2026, 4, 25), water_temp_c=3.0)
    assert s.phase == "pre"
    assert s.intensity == 0.0


def test_pike_active_spawn_at_6c_early_may():
    s = species_spawn_state("pike", date(2026, 5, 5), water_temp_c=6.0)
    assert s.phase == "active"
    assert s.intensity == 1.0
    assert "Нерест щуки" in s.label


def test_pike_post_spawn_at_10c():
    s = species_spawn_state("pike", date(2026, 5, 12), water_temp_c=10.0)
    assert s.phase == "post"
    assert s.intensity == 0.4


def test_pike_no_spawn_above_post_temp():
    """Tw 13°C — pike is past recovery, normal feeding."""
    s = species_spawn_state("pike", date(2026, 5, 20), water_temp_c=13.0)
    assert s.phase == "none"


# -- Perch phases -------------------------------------------------------


def test_perch_active_at_9c():
    s = species_spawn_state("perch", date(2026, 5, 5), water_temp_c=9.0)
    assert s.phase == "active"
    assert "окуня" in s.label.lower()


def test_perch_pre_spawn_at_5c():
    s = species_spawn_state("perch", date(2026, 5, 1), water_temp_c=5.0)
    assert s.phase == "pre"


def test_perch_post_spawn_at_13c():
    s = species_spawn_state("perch", date(2026, 5, 18), water_temp_c=13.0)
    assert s.phase == "post"


# -- Bream phases -------------------------------------------------------


def test_bream_pre_spawn_at_10c_in_may():
    """Bream feeds heavily before spawn — should report pre phase."""
    s = species_spawn_state("bream", date(2026, 5, 15), water_temp_c=10.0)
    assert s.phase == "pre"


def test_bream_active_at_14c():
    s = species_spawn_state("bream", date(2026, 5, 25), water_temp_c=14.0)
    assert s.phase == "active"
    assert "Нерест леща" in s.label


def test_bream_post_at_19c():
    s = species_spawn_state("bream", date(2026, 6, 5), water_temp_c=19.0)
    assert s.phase == "post"


def test_bream_normal_at_21c():
    s = species_spawn_state("bream", date(2026, 6, 15), water_temp_c=21.0)
    assert s.phase == "none"


def test_bream_april_too_early_regardless_of_temp():
    """Even unrealistically warm April water doesn't put bream into spawn."""
    s = species_spawn_state("bream", date(2026, 4, 25), water_temp_c=15.0)
    assert s.phase == "none"


# -- Factor contribution mapping ----------------------------------------


def test_factor_contribution_active_negative():
    s = species_spawn_state("pike", date(2026, 5, 5), water_temp_c=6.0)
    assert species_spawn_factor_contribution(s) < -0.4


def test_factor_contribution_pre_positive():
    """Pre-spawn fattening should bump score (zhor)."""
    s = species_spawn_state("pike", date(2026, 4, 25), water_temp_c=3.0)
    assert species_spawn_factor_contribution(s) > 0.0


def test_factor_contribution_none_zero():
    s = species_spawn_state("pike", date(2026, 1, 15), water_temp_c=1.0)
    assert species_spawn_factor_contribution(s) == 0.0


# -- Profile sanity (ordered thresholds) --------------------------------


@pytest.mark.parametrize("species", ("pike", "perch", "bream"))
def test_profile_thresholds_ordered(species):
    p = SPECIES_SPAWN_PROFILES[species]
    assert p["pre_temp_min"] < p["active_temp_min"]
    assert p["active_temp_min"] < p["active_temp_max"]
    assert p["active_temp_max"] <= p["post_temp_max"]
