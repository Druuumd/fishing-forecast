"""Web Push subscription constructor + dispatch.

A subscription pairs a browser push endpoint with:
  scope: (zone, species) — what forecast to evaluate
  conditions: list[{type, params}] — predicates over a forecast day

The dispatcher evaluates every condition against each forecast day in
the scope; the first day for which all conditions are true triggers a
notification. Dedup is per (subscription, predicted_day).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from pywebpush import WebPushException, webpush
from sqlalchemy import Engine, delete, select
from sqlalchemy.orm import Session

from app.forecast_service import ForecastService, WaterLevelContext
from app.models import PushSubscriptionModel
from app.schemas import ScoreFactor

logger = logging.getLogger("fishing_forecast.push")

SPECIES_RU = {"pike": "щука", "perch": "окунь", "bream": "лещ"}


# ----------------------------------------------------------------------
# Condition registry
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class _Day:
    """Subset of ForecastDay needed by condition evaluators (so the
    registry is decoupled from Pydantic models)."""

    date: date
    score: float
    species: str
    air_temp_c: float
    water_temp_c: float
    wind_speed_m_s: float
    cloud_cover_pct: float
    precipitation_mm: float
    pressure_trend_24h_hpa: float
    daylight_hours: float
    factor_names: set[str]


class ConditionEvaluator:
    type: str = ""

    def matches(self, day: _Day, params: dict, *, today: date) -> bool:  # pragma: no cover
        raise NotImplementedError

    def describe(self, params: dict) -> str:  # pragma: no cover
        raise NotImplementedError


class ScoreMin(ConditionEvaluator):
    type = "score_min"

    def matches(self, day, params, *, today):
        return day.score >= float(params.get("min", 3.5))

    def describe(self, params):
        return f"оценка ≥ {float(params.get('min', 3.5)):.1f}"


class WindMax(ConditionEvaluator):
    type = "wind_max"

    def matches(self, day, params, *, today):
        return day.wind_speed_m_s <= float(params.get("max_m_s", 6.0))

    def describe(self, params):
        return f"ветер ≤ {float(params.get('max_m_s', 6.0)):.1f} м/с"


class NoPressureShock(ConditionEvaluator):
    type = "no_pressure_shock"

    def matches(self, day, params, *, today):
        return "pressure_shock_gate" not in day.factor_names

    def describe(self, params):
        return "без барического шока"


class NoThermalShock(ConditionEvaluator):
    type = "no_thermal_shock"

    def matches(self, day, params, *, today):
        return "thermal_shock_gate" not in day.factor_names

    def describe(self, params):
        return "без термошока"


class NoSevereWeather(ConditionEvaluator):
    type = "no_severe_weather"

    def matches(self, day, params, *, today):
        return "severe_weather_gate" not in day.factor_names

    def describe(self, params):
        return "без шторма"


class NoPrecipitation(ConditionEvaluator):
    type = "no_precipitation"

    def matches(self, day, params, *, today):
        return day.precipitation_mm <= float(params.get("max_mm", 0.5))

    def describe(self, params):
        return f"осадки ≤ {float(params.get('max_mm', 0.5)):.1f} мм"


class WaterTempMin(ConditionEvaluator):
    type = "water_temp_min"

    def matches(self, day, params, *, today):
        return day.water_temp_c >= float(params.get("min", 8.0))

    def describe(self, params):
        return f"вода ≥ {float(params.get('min', 8.0)):.1f}°C"


class WaterTempMax(ConditionEvaluator):
    type = "water_temp_max"

    def matches(self, day, params, *, today):
        return day.water_temp_c <= float(params.get("max", 24.0))

    def describe(self, params):
        return f"вода ≤ {float(params.get('max', 24.0)):.1f}°C"


class PressureStable(ConditionEvaluator):
    type = "pressure_stable"

    def matches(self, day, params, *, today):
        return abs(day.pressure_trend_24h_hpa) <= float(params.get("delta_max", 4.0))

    def describe(self, params):
        return f"давление стабильно (|ΔP/24h| ≤ {float(params.get('delta_max', 4.0)):.1f} hPa)"


class CloudMax(ConditionEvaluator):
    type = "cloud_max"

    def matches(self, day, params, *, today):
        return day.cloud_cover_pct <= float(params.get("pct", 70.0))

    def describe(self, params):
        return f"облачность ≤ {float(params.get('pct', 70.0)):.0f}%"


class DaylightMin(ConditionEvaluator):
    type = "daylight_min"

    def matches(self, day, params, *, today):
        return day.daylight_hours >= float(params.get("hours", 12.0))

    def describe(self, params):
        return f"световой день ≥ {float(params.get('hours', 12.0)):.1f} ч"


class LookaheadMaxDays(ConditionEvaluator):
    type = "lookahead_max_days"

    def matches(self, day, params, *, today):
        max_d = int(params.get("days", 5))
        return (day.date - today).days <= max_d

    def describe(self, params):
        return f"в ближайшие {int(params.get('days', 5))} дней"


class WeekendOnly(ConditionEvaluator):
    type = "weekend_only"

    def matches(self, day, params, *, today):
        return day.date.weekday() >= 5  # 5=Sat, 6=Sun

    def describe(self, params):
        return "только в выходные"


CONDITION_REGISTRY: dict[str, ConditionEvaluator] = {
    e.type: e
    for e in [
        ScoreMin(), WindMax(), NoPressureShock(), NoThermalShock(),
        NoSevereWeather(), NoPrecipitation(), WaterTempMin(), WaterTempMax(),
        PressureStable(), CloudMax(), DaylightMin(), LookaheadMaxDays(),
        WeekendOnly(),
    ]
}


# ----------------------------------------------------------------------
# Subscription DTO + repository
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class PushSubscription:
    id: str
    user_id: str
    endpoint: str
    p256dh: str
    auth_secret: str
    name: str | None
    scope_zone: str | None
    scope_species: str | None
    conditions: list[dict]
    last_notified_for_day: date | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DispatchOutcome:
    sent: int
    skipped_no_match: int
    skipped_duplicate: int
    failed: int
    expired_pruned: int


class PushSubscriptionRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def upsert(
        self,
        *,
        user_id: str,
        endpoint: str,
        p256dh: str,
        auth_secret: str,
        name: str | None,
        scope_zone: str | None,
        scope_species: str | None,
        conditions: list[dict],
    ) -> PushSubscription:
        now = datetime.now(UTC)
        conditions_json = json.dumps(conditions, ensure_ascii=False)
        with Session(self._engine) as session:
            row = session.execute(
                select(PushSubscriptionModel).where(PushSubscriptionModel.endpoint == endpoint)
            ).scalar_one_or_none()
            if row is None:
                row = PushSubscriptionModel(
                    id=uuid4().hex,
                    user_id=user_id,
                    endpoint=endpoint,
                    p256dh=p256dh,
                    auth_secret=auth_secret,
                    name=name,
                    scope_zone=scope_zone,
                    scope_species=scope_species,
                    conditions_json=conditions_json,
                    last_notified_for_day=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.user_id = user_id
                row.p256dh = p256dh
                row.auth_secret = auth_secret
                row.name = name
                row.scope_zone = scope_zone
                row.scope_species = scope_species
                row.conditions_json = conditions_json
                row.updated_at = now
            session.commit()
            return self._to_dto(row)

    def list_by_user(self, user_id: str) -> list[PushSubscription]:
        with Session(self._engine) as session:
            rows = session.execute(
                select(PushSubscriptionModel)
                .where(PushSubscriptionModel.user_id == user_id)
                .order_by(PushSubscriptionModel.created_at.asc())
            ).scalars().all()
        return [self._to_dto(r) for r in rows]

    def list_all(self) -> list[PushSubscription]:
        with Session(self._engine) as session:
            rows = session.execute(select(PushSubscriptionModel)).scalars().all()
        return [self._to_dto(r) for r in rows]

    def delete(self, *, sub_id: str, user_id: str) -> bool:
        with Session(self._engine) as session:
            result = session.execute(
                delete(PushSubscriptionModel)
                .where(PushSubscriptionModel.id == sub_id)
                .where(PushSubscriptionModel.user_id == user_id)
            )
            session.commit()
            return result.rowcount > 0

    def delete_by_endpoint(self, endpoint: str) -> bool:
        with Session(self._engine) as session:
            result = session.execute(
                delete(PushSubscriptionModel).where(PushSubscriptionModel.endpoint == endpoint)
            )
            session.commit()
            return result.rowcount > 0

    def mark_notified(self, sub_id: str, day: date) -> None:
        with Session(self._engine) as session:
            row = session.get(PushSubscriptionModel, sub_id)
            if row is not None:
                row.last_notified_for_day = day
                row.updated_at = datetime.now(UTC)
                session.commit()

    @staticmethod
    def _to_dto(row: PushSubscriptionModel) -> PushSubscription:
        try:
            conditions = json.loads(row.conditions_json or "[]")
            if not isinstance(conditions, list):
                conditions = []
        except json.JSONDecodeError:
            conditions = []
        return PushSubscription(
            id=row.id,
            user_id=row.user_id,
            endpoint=row.endpoint,
            p256dh=row.p256dh,
            auth_secret=row.auth_secret,
            name=row.name,
            scope_zone=row.scope_zone,
            scope_species=row.scope_species,
            conditions=conditions,
            last_notified_for_day=row.last_notified_for_day,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


# ----------------------------------------------------------------------
# Push service
# ----------------------------------------------------------------------


def describe_conditions(conditions: list[dict]) -> str:
    """Human-readable summary used in notification body / UI preview."""
    if not conditions:
        return "без дополнительных условий"
    parts = []
    for c in conditions:
        evaluator = CONDITION_REGISTRY.get(c.get("type"))
        if evaluator is None:
            parts.append(f"?{c.get('type')}")
            continue
        parts.append(evaluator.describe(c.get("params", {})))
    return "; ".join(parts)


class PushService:
    def __init__(
        self,
        *,
        repository: PushSubscriptionRepository,
        vapid_private_key_pem: str,
        vapid_subject: str,
        forecast_service: ForecastService,
        lookahead_days: int = 5,
    ) -> None:
        self._repository = repository
        self._vapid_pem = vapid_private_key_pem
        self._vapid_subject = vapid_subject
        self._forecast_service = forecast_service
        self._lookahead_days = lookahead_days

    @property
    def enabled(self) -> bool:
        return bool(self._vapid_pem)

    def send(
        self,
        *,
        sub: PushSubscription,
        title: str,
        body: str,
        data: dict | None = None,
    ) -> bool:
        if not self.enabled:
            logger.warning("push_disabled_no_vapid")
            return False
        payload = json.dumps({"title": title, "body": body, "data": data or {}})
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth_secret},
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=self._vapid_pem,
                vapid_claims={"sub": self._vapid_subject},
                ttl=86400,
            )
            return True
        except WebPushException as exc:
            status_code = getattr(exc.response, "status_code", None) if exc.response else None
            if status_code in (404, 410):
                logger.info("push_endpoint_gone", extra={"sub_id": sub.id, "status": status_code})
                self._repository.delete_by_endpoint(sub.endpoint)
                return False
            logger.warning(
                "push_send_failed",
                extra={"sub_id": sub.id, "status": status_code, "err": str(exc)},
            )
            return False
        except Exception:
            logger.exception("push_send_unexpected", extra={"sub_id": sub.id})
            return False

    def dispatch_for_all(
        self,
        *,
        snapshots_loader,
        water_level: WaterLevelContext | None,
    ) -> DispatchOutcome:
        outcome = {
            "sent": 0, "skipped_no_match": 0, "skipped_duplicate": 0,
            "failed": 0, "expired_pruned": 0,
        }
        if not self.enabled:
            return DispatchOutcome(**outcome)
        today = datetime.now(UTC).date()
        for sub in self._repository.list_all():
            best = self._best_day_for_subscription(
                sub=sub, snapshots_loader=snapshots_loader,
                water_level=water_level, today=today,
            )
            if best is None:
                outcome["skipped_no_match"] += 1
                continue
            if sub.last_notified_for_day == best["date"]:
                outcome["skipped_duplicate"] += 1
                continue
            title, body = self._format_alert(sub=sub, day=best)
            ok = self.send(
                sub=sub, title=title, body=body,
                data={
                    "date": str(best["date"]), "zone": sub.scope_zone,
                    "species": best["species"], "score": best["score"],
                },
            )
            if ok:
                self._repository.mark_notified(sub.id, best["date"])
                outcome["sent"] += 1
            else:
                outcome["failed"] += 1
        return DispatchOutcome(**outcome)

    def _best_day_for_subscription(
        self, *, sub: PushSubscription, snapshots_loader,
        water_level: WaterLevelContext | None, today: date,
    ) -> dict | None:
        snapshots = snapshots_loader(sub.scope_zone)
        if not snapshots:
            return None
        species_list = [sub.scope_species] if sub.scope_species else ["pike", "perch", "bream"]
        zone_profile = self._forecast_service._zone_profile(sub.scope_zone)
        best: dict | None = None
        for fish_species in species_list:
            for snap in snapshots[: self._lookahead_days]:
                if snap.day < today:
                    continue
                score, _, factors = self._forecast_service._score_with_factors(
                    fish_species, snap, water_level=water_level, zone=zone_profile,
                )
                day_view = _Day(
                    date=snap.day, score=round(score, 2), species=fish_species,
                    air_temp_c=snap.air_temp_c, water_temp_c=snap.water_temp_c,
                    wind_speed_m_s=snap.wind_speed_m_s,
                    cloud_cover_pct=snap.cloud_cover_pct,
                    precipitation_mm=snap.precipitation_mm,
                    pressure_trend_24h_hpa=snap.pressure_trend_24h_hpa,
                    daylight_hours=snap.daylight_hours,
                    factor_names={f.name for f in factors},
                )
                if not self._matches_all(day_view, sub.conditions, today=today):
                    continue
                if best is None or day_view.score > best["score"]:
                    best = {"date": day_view.date, "score": day_view.score, "species": fish_species}
        return best

    @staticmethod
    def _matches_all(day: _Day, conditions: list[dict], *, today: date) -> bool:
        for c in conditions:
            evaluator = CONDITION_REGISTRY.get(c.get("type"))
            if evaluator is None:
                continue  # unknown condition: skip rather than fail-shut
            try:
                if not evaluator.matches(day, c.get("params", {}) or {}, today=today):
                    return False
            except Exception:
                logger.exception("condition_evaluator_failed", extra={"type": c.get("type")})
                return False
        return True

    def _format_alert(self, *, sub: PushSubscription, day: dict) -> tuple[str, str]:
        species_ru = SPECIES_RU.get(day["species"], day["species"])
        title = f"🎣 {sub.name or 'Хороший клёв'}: {species_ru} {day['score']:.1f}"
        when = day["date"].strftime("%d.%m")
        zone_part = f"в зоне {sub.scope_zone}" if sub.scope_zone else "по всей акватории"
        body = f"{when} {species_ru}: {day['score']:.1f}/5 {zone_part}"
        return title, body
