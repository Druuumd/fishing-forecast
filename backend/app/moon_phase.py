"""Lunar phase decomposition.

The raw 0..1 ``moon_phase`` we compute from day ordinals is enough for
the score formula's symmetry trick, but anglers think in different
terms — растущая/убывающая, ближайшее новолуние/полнолуние, освещённость
в процентах. This module exposes those derived fields so:

  * the UI can label the phase in plain Russian,
  * the push-notification constructor can offer "только растущая луна"
    as a condition,
  * future regression / ML can pull illumination % directly.

Math is the standard textbook approximation; we don't need ephemeris-
grade accuracy because synodic period is 29.53 days and we round to
named phases anyway.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


SYNODIC_PERIOD_DAYS = 29.530588853  # mean lunation


# Phase boundaries in 'age' (days since new moon). Standard 8-segment
# split: each named phase covers ~3.69 days, then the symmetric pair
# extends across the boundary. Centred on the canonical days.
_PHASE_BOUNDARIES = [
    (0.0, "new"),                  # 0–1 days
    (1.84, "waxing_crescent"),     # 1.84–5.54
    (5.54, "first_quarter"),       # 5.54–9.22
    (9.22, "waxing_gibbous"),      # 9.22–12.91
    (12.91, "full"),               # 12.91–16.61
    (16.61, "waning_gibbous"),     # 16.61–20.30
    (20.30, "last_quarter"),       # 20.30–23.99
    (23.99, "waning_crescent"),    # 23.99–27.69
    (27.69, "new"),                # 27.69 → wrap to next new moon
]

PHASE_LABEL_RU = {
    "new": "Новолуние",
    "waxing_crescent": "Растущий месяц",
    "first_quarter": "Первая четверть",
    "waxing_gibbous": "Растущая (горбатая)",
    "full": "Полнолуние",
    "waning_gibbous": "Убывающая (горбатая)",
    "last_quarter": "Последняя четверть",
    "waning_crescent": "Старый месяц",
}


@dataclass(frozen=True)
class MoonState:
    """Decomposed lunar state.

    Fields:
      * phase_value: original [0,1] value (legacy compatibility).
      * age_days: days since the most recent new moon, [0, 29.53).
      * illumination_pct: visible disc fraction, [0, 100].
      * phase_kind: one of PHASE_LABEL_RU keys.
      * phase_label: Russian label for the UI.
      * growing: True if the moon is waxing (between new and full).
    """
    phase_value: float
    age_days: float
    illumination_pct: float
    phase_kind: str
    phase_label: str
    growing: bool


def decompose(phase_value: float) -> MoonState:
    """Map a [0,1] phase fraction to a full MoonState.

    phase_value is interpreted as fraction of the synodic period since
    the last new moon (matches our existing snapshot.moon_phase).
    """
    phase_value = max(0.0, min(1.0, phase_value))
    age_days = phase_value * SYNODIC_PERIOD_DAYS

    # Illumination % follows a smooth cosine: 0 at new, 100 at full,
    # back to 0 at next new. Simple model — accurate to a few % vs
    # ephemeris values.
    illumination = 0.5 * (1.0 - math.cos(2 * math.pi * phase_value)) * 100.0

    # Find the named phase by walking boundaries.
    kind = "new"
    for boundary_age, name in _PHASE_BOUNDARIES:
        if age_days >= boundary_age:
            kind = name
        else:
            break

    growing = phase_value < 0.5  # waxing half of the cycle

    return MoonState(
        phase_value=round(phase_value, 4),
        age_days=round(age_days, 2),
        illumination_pct=round(illumination, 1),
        phase_kind=kind,
        phase_label=PHASE_LABEL_RU[kind],
        growing=growing,
    )
