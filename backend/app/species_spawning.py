"""Species-specific spawning windows.

The general spawning ban (25.04 – 25.06) is a legal restriction for all
species. But each species has its own physiological spawn period
governed primarily by water temperature, not the calendar. During the
active spawn the fish stops feeding for 3–10 days; during post-spawn
recovery the bite is unstable for another 5–7 days; before the spawn
("pre-spawn fattening") activity is *elevated*.

This module captures those phases so the forecast can:
  * dampen score when a species is actively spawning ("не клюёт — нерест"),
  * lift score during pre-spawn aggression,
  * produce per-species advisories the angler can act on.

Inputs we have available:
  * ``species`` — pike / perch / bream
  * ``day`` — calendar date (used as a coarse gate; in Eastern Siberia
    spawning never happens outside specific months regardless of temp)
  * ``water_temp_c`` — the actual physiological trigger; bays warm at
    different rates so the same date sees different states across zones
  * ``zone_code`` — currently informational; future versions can adjust
    thresholds per archetype (shallow bays trigger earlier).

We deliberately keep this module pure — no I/O, no DB. Easy to test,
easy to reuse from both the scoring layer and the warnings layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


# Per-species temperature bands and calendar gates. Numbers reflect
# field reports for Krasnoyarsk reservoir; close to the standard
# ranges in Russian ichthyological literature.
SPECIES_SPAWN_PROFILES: dict[str, dict] = {
    "pike": {
        "pre_temp_min": 2.0,    # below 2°C fish is dormant
        "active_temp_min": 4.0,
        "active_temp_max": 9.0,
        "post_temp_max": 11.0,
        "calendar_months": {4, 5},
        "label": "Нерест щуки",
        "body_active": (
            "Щука нерестится в мелководных бухтах при +4…+9°C. Активный клёв "
            "затихает на 5–10 дней после икрометания. После прогрева воды "
            "до +10°C начинается посленерестовый жор."
        ),
        "body_post": (
            "Посленерестовое восстановление щуки: клёв нестабильный 5–7 дней, "
            "затем начинается жор."
        ),
    },
    "perch": {
        "pre_temp_min": 4.0,
        "active_temp_min": 7.0,
        "active_temp_max": 12.0,
        "post_temp_max": 14.0,
        "calendar_months": {4, 5},
        "label": "Нерест окуня",
        "body_active": (
            "Окунь нерестится при +7…+12°C — мечет ленты икры на затопленный "
            "кустарник и водоросли. Клёв капризный 5–7 дней, затем активный "
            "посленерестовый период."
        ),
        "body_post": (
            "Посленерестовое восстановление окуня: переход на ловлю стайных "
            "котлов на бровках и косах."
        ),
    },
    "bream": {
        "pre_temp_min": 8.0,
        "active_temp_min": 12.0,
        "active_temp_max": 18.0,
        "post_temp_max": 20.0,
        "calendar_months": {5, 6},
        "label": "Нерест леща",
        "body_active": (
            "Лещ нерестится в прибрежной траве и заросших бухтах при +12…+18°C. "
            "В период активного нереста почти не питается. Через 7–10 дней "
            "начинается жор у бровок и свалов."
        ),
        "body_post": (
            "Посленерестовое восстановление леща: ловите на привалах у "
            "бровок 4–8 м, особенно в Сыдинском, Дербинском, Ижульском заливах."
        ),
    },
}


@dataclass(frozen=True)
class SpawnState:
    """Outcome of evaluating spawn state for a (species, day, Tw) tuple.

    phase ∈ {"none", "pre", "active", "post"}.
      * "none"   — fish is feeding normally (pre-spawn fattening *not*
                   detected, e.g. winter or full summer).
      * "pre"    — calendar window matched but Tw still below active
                   trigger; fish actively fattens before spawning.
      * "active" — full spawning, fish is not feeding.
      * "post"   — recovery, bite gradually returns.
    """
    phase: str
    intensity: float  # 0..1: how disruptive to the bite (0 if pre/none)
    label: str
    body: str


def species_spawn_state(
    species: str,
    day: date,
    water_temp_c: float,
    zone_code: str | None = None,
) -> SpawnState:
    profile = SPECIES_SPAWN_PROFILES.get(species)
    if profile is None:
        return SpawnState(phase="none", intensity=0.0, label="", body="")

    if day.month not in profile["calendar_months"]:
        return SpawnState(phase="none", intensity=0.0, label="", body="")

    if water_temp_c < profile["pre_temp_min"]:
        # Fish still in winter/dormant mode — no special handling here.
        return SpawnState(phase="none", intensity=0.0, label="", body="")

    if water_temp_c < profile["active_temp_min"]:
        # Pre-spawn fattening: temperature climbing toward trigger but
        # not there yet. We DON'T flag a warning, but the score factor
        # gets a small positive bump because fish is actively feeding.
        return SpawnState(phase="pre", intensity=0.0, label="", body="")

    if water_temp_c <= profile["active_temp_max"]:
        return SpawnState(
            phase="active",
            intensity=1.0,
            label=profile["label"],
            body=profile["body_active"],
        )

    if water_temp_c <= profile["post_temp_max"]:
        return SpawnState(
            phase="post",
            intensity=0.4,
            label=f"{profile['label']} (восстановление)",
            body=profile["body_post"],
        )

    # Past the post-spawn temp window — back to normal.
    return SpawnState(phase="none", intensity=0.0, label="", body="")


def species_spawn_factor_contribution(state: SpawnState) -> float:
    """Map a SpawnState to a score-factor contribution.

    Active spawn: −0.55 (fish doesn't feed; this is not a multiplicative
    gate because the bite isn't *physically zero* — some opportunistic
    bites still happen, especially small pre-spawn females. But it's a
    strong negative.)

    Post-spawn recovery: −0.20 (bite unstable but returning).

    Pre-spawn fattening: +0.20 (legendary "pre-spawn zhor" of pike, the
    best fishing window of the year for predators).

    None: 0.
    """
    if state.phase == "active":
        return -0.55
    if state.phase == "post":
        return -0.20
    if state.phase == "pre":
        return 0.20
    return 0.0
