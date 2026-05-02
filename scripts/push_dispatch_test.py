"""Verify the constructor: build a subscription with a few conditions,
ask the service which day matches. We don't actually send a push (no
browser endpoint) — just exercise the matching pipeline.
"""
import json
import logging
from datetime import UTC, datetime
from app.main import (
    forecast_service,
    push_repository,
    push_service,
    water_level_service,
    weather_repository,
)
from app.forecast_service import WaterLevelContext
from app.push_service import PushSubscription, describe_conditions

logging.basicConfig(level=logging.INFO)
today = datetime.now(UTC).date()


def snapshots_for(zone):
    if zone:
        rows = weather_repository.get_window(start_day=today, days=7, zone=zone)
        if len(rows) >= 7:
            return rows
    return weather_repository.get_window(start_day=today, days=7, zone="default")


water_state = water_level_service.current_state(today=today)
wl = WaterLevelContext(
    latest_level_m=water_state.latest_level_m,
    trend_7d_m=water_state.trend_7d_m,
    source=water_state.source,
    is_fresh=water_state.is_fresh,
)

scenarios = [
    {
        "label": "Лещ на Сыде, score >= 2.0, без шторма",
        "scope_zone": "syda",
        "scope_species": "bream",
        "conditions": [
            {"type": "score_min", "params": {"min": 2.0}},
            {"type": "no_severe_weather", "params": {}},
        ],
    },
    {
        "label": "Любой вид, любая зона, выходные, без барошока",
        "scope_zone": None,
        "scope_species": None,
        "conditions": [
            {"type": "weekend_only", "params": {}},
            {"type": "no_pressure_shock", "params": {}},
            {"type": "score_min", "params": {"min": 2.5}},
        ],
    },
    {
        "label": "Щука в Бирюсе, ветер ≤ 5, давление стабильно",
        "scope_zone": "biryusa",
        "scope_species": "pike",
        "conditions": [
            {"type": "wind_max", "params": {"max_m_s": 5.0}},
            {"type": "pressure_stable", "params": {"delta_max": 4.0}},
            {"type": "score_min", "params": {"min": 1.5}},
        ],
    },
    {
        "label": "Невыполнимое: лещ при Tw ≥ 18°C (сейчас холодно)",
        "scope_zone": "syda",
        "scope_species": "bream",
        "conditions": [
            {"type": "water_temp_min", "params": {"min": 18.0}},
        ],
    },
]

for s in scenarios:
    print(f"\n=== {s['label']} ===")
    print(f"   conditions: {describe_conditions(s['conditions'])}")
    sub = PushSubscription(
        id="test", user_id="test", endpoint="https://example.test/none",
        p256dh="x" * 30, auth_secret="x" * 20,
        name=None, scope_zone=s["scope_zone"], scope_species=s["scope_species"],
        conditions=s["conditions"], last_notified_for_day=None,
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )
    best = push_service._best_day_for_subscription(
        sub=sub, snapshots_loader=snapshots_for, water_level=wl, today=today,
    )
    if best:
        print(f"   ✅ best day: {best['date']} score={best['score']} {best['species']}")
    else:
        print(f"   ❌ no day matches all conditions in next {push_service._lookahead_days} days")
