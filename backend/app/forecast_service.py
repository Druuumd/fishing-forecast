import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Callable
from uuid import uuid4

from app.catch_repository import CatchRepository
from app.schemas import CatchCreate, CatchRecord, FishSpecies, ForecastDay, ForecastResponse, ScoreFactor, utcnow


# Bay-zone registry for Krasnoyarsk reservoir.
# Each entry is a "passport" that interprets the atmospheric snapshot
# through the bay's depth/exposure/inflow characteristics:
#   water_temp_offset_c — Δ Tw vs reservoir-wide observation
#   ice_freeze_temp_c, ice_thaw_temp_c — water-temp thresholds
#   ice_months / transition_months — calendar windows when those
#     thresholds activate "ice" or "transition" regime
#   level_sensitivity — multiplier for the water-level factor (shallow
#     bays: drawdown exposes spawning shallows visibly; deep bays:
#     dampened)
#   species_base_bias — habitat suitability bonus/penalty
_BASELINE_ZONE_PROFILE: dict = {
    "code": None,
    "label": None,
    "water_temp_offset_c": 0.0,
    "ice_freeze_temp_c": 1.0,
    "ice_thaw_temp_c": 4.0,
    "ice_months": {11, 12, 1, 2, 3, 4},
    "transition_months": {10, 11, 4, 5},
    "level_sensitivity": 1.0,
    "species_base_bias": {},
}


def _bay(
    code: str,
    label: str,
    *,
    archetype: str,
    bream: float = 0.0,
    pike: float = 0.0,
    perch: float = 0.0,
) -> dict:
    """Compose a bay profile from a thermal/depth archetype + species bias."""
    archetypes = {
        # Shallow, sandy/gentle banks, fast-warming. Drawdown exposes
        # spawning shallows. Bream/pike spawning bays.
        "shallow_warm": {
            "water_temp_offset_c": +1.5,
            "ice_freeze_temp_c": 1.5,
            "ice_thaw_temp_c": 4.5,
            "ice_months": {11, 12, 1, 2, 3, 4, 5},
            "transition_months": {10, 11, 4, 5, 6},
            "level_sensitivity": 1.5,
        },
        # Narrow shallow inlets, modest warming, used for spawning.
        "narrow_shallow": {
            "water_temp_offset_c": +1.0,
            "ice_freeze_temp_c": 1.4,
            "ice_thaw_temp_c": 4.3,
            "ice_months": {11, 12, 1, 2, 3, 4, 5},
            "transition_months": {10, 11, 4, 5, 6},
            "level_sensitivity": 1.4,
        },
        # Boggy, slow flow, very shallow — major spawning grounds for
        # cyprinids. Strong drawdown effect.
        "swampy_shallow": {
            "water_temp_offset_c": +1.6,
            "ice_freeze_temp_c": 1.6,
            "ice_thaw_temp_c": 4.6,
            "ice_months": {11, 12, 1, 2, 3, 4, 5},
            "transition_months": {10, 11, 4, 5, 6},
            "level_sensitivity": 1.6,
        },
        # Medium depth, moderate temperatures. Balanced fishery.
        "medium_balanced": {
            "water_temp_offset_c": +0.4,
            "ice_freeze_temp_c": 1.1,
            "ice_thaw_temp_c": 4.1,
            "ice_months": {11, 12, 1, 2, 3, 4},
            "transition_months": {10, 11, 4, 5},
            "level_sensitivity": 1.1,
        },
        # Mixed depths, irregular shoreline (fjord-like).
        "irregular_mixed": {
            "water_temp_offset_c": +0.3,
            "ice_freeze_temp_c": 1.0,
            "ice_thaw_temp_c": 4.0,
            "ice_months": {11, 12, 1, 2, 3, 4},
            "transition_months": {10, 11, 4, 5},
            "level_sensitivity": 1.0,
        },
        # Steep forested banks, medium-deep, cooler.
        "steep_cool": {
            "water_temp_offset_c": -0.6,
            "ice_freeze_temp_c": 0.9,
            "ice_thaw_temp_c": 3.8,
            "ice_months": {11, 12, 1, 2, 3, 4},
            "transition_months": {10, 11, 4, 5},
            "level_sensitivity": 0.9,
        },
        # Rocky/cliff banks, medium-deep, cool. Trolling/sport water.
        "rocky_deep_cool": {
            "water_temp_offset_c": -0.8,
            "ice_freeze_temp_c": 0.9,
            "ice_thaw_temp_c": 3.8,
            "ice_months": {11, 12, 1, 2, 3, 4},
            "transition_months": {10, 11, 4, 5},
            "level_sensitivity": 0.9,
        },
        # Deep, cold tributary mouth, navigable.
        "deep_cold": {
            "water_temp_offset_c": -1.2,
            "ice_freeze_temp_c": 0.8,
            "ice_thaw_temp_c": 3.6,
            "ice_months": {11, 12, 1, 2, 3, 4},
            "transition_months": {11, 12, 4, 5},
            "level_sensitivity": 0.8,
        },
        # Open main channel along the old Yenisei riverbed.
        "main_channel": {
            "water_temp_offset_c": -1.5,
            "ice_freeze_temp_c": 0.7,
            "ice_thaw_temp_c": 3.5,
            "ice_months": {12, 1, 2, 3, 4},
            "transition_months": {11, 12, 4, 5},
            "level_sensitivity": 0.7,
        },
    }
    base = archetypes[archetype]
    return {
        "code": code,
        "label": label,
        "archetype": archetype,
        **base,
        "species_base_bias": {"bream": bream, "pike": pike, "perch": perch},
    }


_BAY_REGISTRY: dict[str, dict] = {
    # South / shallow / warm — bream-prime habitat.
    "syda": _bay(
        "syda", "Сыдинский залив (р. Сыда)",
        archetype="shallow_warm", bream=0.35, pike=0.15, perch=0.10,
    ),
    "ubey": _bay(
        "ubey", "Убейский залив (р. Убей)",
        archetype="shallow_warm", bream=0.30, pike=0.10, perch=0.10,
    ),
    "karasug": _bay(
        "karasug", "Карасугский залив (р. Карасуг)",
        archetype="shallow_warm", bream=0.30, pike=0.20, perch=0.10,
    ),
    "yezagash": _bay(
        "yezagash", "Езагашский залив (р. Езагаш)",
        archetype="swampy_shallow", bream=0.40, pike=0.20, perch=0.10,
    ),
    # Narrow shallow inlets.
    "anash": _bay(
        "anash", "Анашский залив (р. Анаша)",
        archetype="narrow_shallow", bream=0.25, pike=0.15, perch=0.10,
    ),
    "koma": _bay(
        "koma", "Комский залив (р. Кома)",
        archetype="narrow_shallow", bream=0.20, pike=0.10, perch=0.05,
    ),
    # Medium-depth balanced bays.
    "ogur": _bay(
        "ogur", "Огурский залив (р. Огур)",
        archetype="medium_balanced", bream=0.15, pike=0.10, perch=0.05,
    ),
    "izhul": _bay(
        "izhul", "Ижульский залив (р. Ижуль)",
        archetype="medium_balanced", bream=0.10, pike=0.05, perch=0.05,
    ),
    "derbino": _bay(
        "derbino", "Дербинский залив (р. Дербина)",
        archetype="irregular_mixed", bream=0.05, pike=0.05, perch=0.05,
    ),
    # Cool, deeper.
    "sisim": _bay(
        "sisim", "Сисимский залив (р. Сисим)",
        archetype="steep_cool", bream=-0.15, pike=0.10, perch=0.05,
    ),
    "biryusa": _bay(
        "biryusa", "Бирюсинский залив (р. Бирюса)",
        archetype="rocky_deep_cool", bream=-0.20, pike=0.10, perch=0.05,
    ),
    "tubinsky": _bay(
        "tubinsky", "Тубинский залив (р. Туба)",
        archetype="deep_cold", bream=-0.25, pike=0.15, perch=0.05,
    ),
    # Open water / main channel.
    "main_channel": _bay(
        "main_channel", "Главное русло (открытая часть)",
        archetype="main_channel", bream=-0.30, pike=0.10, perch=0.05,
    ),
}


@dataclass(frozen=True)
class WeatherSnapshot:
    day: date
    air_temp_c: float
    pressure_hpa: float
    water_temp_c: float
    wind_speed_m_s: float
    wind_direction_deg: float
    moon_phase: float
    cloud_cover_pct: float = 0.0
    precipitation_mm: float = 0.0
    humidity_pct: float = 0.0
    pressure_trend_6h_hpa: float = 0.0
    pressure_trend_24h_hpa: float = 0.0
    daylight_hours: float = 12.0
    sunrise: datetime | None = None
    sunset: datetime | None = None


@dataclass(frozen=True)
class WaterLevelContext:
    """Aggregate current reservoir state applied to each forecast day."""
    latest_level_m: float
    trend_7d_m: float
    source: str
    is_fresh: bool


class ForecastService:
    def __init__(
        self,
        catch_repository: CatchRepository,
        historical_snapshot_loader: Callable[[date], list[WeatherSnapshot]] | None = None,
        region: str = "krasnoyarsk",
        region_elevation_m: float | None = None,
        location_lat: float = 55.0,
        location_lon: float = 91.7,
    ) -> None:
        self._catch_repository = catch_repository
        self._historical_snapshot_loader = historical_snapshot_loader
        self._region = region.lower().strip()
        self._location_lat = location_lat
        self._location_lon = location_lon
        # Median water-edge elevation above sea level. Defaults reflect each
        # region's typical fishing surface; override via constructor / settings.
        defaults_m = {"krasnoyarsk": 234.0, "northwest": 10.0}
        self._region_elevation_m = (
            region_elevation_m if region_elevation_m is not None else defaults_m.get(self._region, 150.0)
        )

    def build_forecast(self, species: FishSpecies | None) -> ForecastResponse:
        snapshots = self._daily_snapshots()
        return self.build_forecast_from_snapshots(
            snapshots=snapshots,
            species=species,
            stale=False,
            last_updated_at=utcnow(),
        )

    def build_forecast_from_snapshots(
        self,
        snapshots: list[WeatherSnapshot],
        species: FishSpecies | None,
        stale: bool,
        last_updated_at: datetime | None,
        species_bias_map: dict[str, float] | None = None,
        water_level: WaterLevelContext | None = None,
        zone: str | None = None,
        apply_zone_temp_offset: bool = True,
    ) -> ForecastResponse:
        species_list: list[FishSpecies] = [species] if species else ["pike", "perch", "bream"]
        species_bias_map = species_bias_map or {}
        zone_profile = self._zone_profile(zone)
        # When the snapshot already comes from a zone-specific Open-Meteo
        # call, its water/air temps reflect bay reality — no need to add
        # the heuristic Δ°C offset on top.
        if not apply_zone_temp_offset and zone_profile.get("code"):
            zone_profile = {**zone_profile, "water_temp_offset_c": 0.0}
        days: list[ForecastDay] = []
        for fish_species in species_list:
            for snapshot in snapshots:
                score, confidence, factors = self._score_with_factors(
                    fish_species,
                    snapshot,
                    bias=species_bias_map.get(fish_species, 0.0),
                    water_level=water_level,
                    zone=zone_profile,
                )
                # Decompose the raw moon phase fraction into the semantic
                # fields the UI and push constructor work with.
                from app.moon_phase import decompose as decompose_moon
                moon = decompose_moon(snapshot.moon_phase)

                # Zone-adjusted water temp drives the advisory the same way
                # it drives the thermocline gate inside scoring. Recent wind
                # window: prefer the 3 snapshots immediately preceding this
                # forecast day if available (Open-Meteo gives past_days=2
                # so the buffer naturally contains them).
                zone_water_temp = snapshot.water_temp_c + zone_profile["water_temp_offset_c"]
                recent_winds = [
                    s.wind_speed_m_s for s in snapshots
                    if s.day < snapshot.day and (snapshot.day - s.day).days <= 3
                ]
                tc = self.thermocline_advisory(
                    water_temp_c=zone_water_temp,
                    zone=zone_profile,
                    recent_wind_speeds_m_s=recent_winds or None,
                )
                bh = self.best_hours(snapshot)
                days.append(
                    ForecastDay(
                        date=snapshot.day,
                        species=fish_species,
                        score=score,
                        confidence=confidence,
                        air_temp_c=snapshot.air_temp_c,
                        pressure_hpa=snapshot.pressure_hpa,
                        surface_pressure_hpa=round(
                            self._surface_pressure_hpa(snapshot.air_temp_c, snapshot.pressure_hpa), 1
                        ),
                        water_temp_c=snapshot.water_temp_c,
                        wind_speed_m_s=snapshot.wind_speed_m_s,
                        wind_direction_deg=snapshot.wind_direction_deg,
                        moon_phase=snapshot.moon_phase,
                        moon_age_days=moon.age_days,
                        moon_illumination_pct=moon.illumination_pct,
                        moon_phase_kind=moon.phase_kind,
                        moon_phase_label=moon.phase_label,
                        moon_growing=moon.growing,
                        cloud_cover_pct=snapshot.cloud_cover_pct,
                        precipitation_mm=snapshot.precipitation_mm,
                        humidity_pct=snapshot.humidity_pct,
                        pressure_trend_6h_hpa=snapshot.pressure_trend_6h_hpa,
                        pressure_trend_24h_hpa=snapshot.pressure_trend_24h_hpa,
                        daylight_hours=snapshot.daylight_hours,
                        sunrise=snapshot.sunrise,
                        sunset=snapshot.sunset,
                        water_level_m=water_level.latest_level_m if water_level else None,
                        water_level_trend_7d_m=water_level.trend_7d_m if water_level else 0.0,
                        water_level_source=water_level.source if water_level else None,
                        zone=zone_profile["code"],
                        zone_label=zone_profile["label"],
                        thermocline_strength=tc["strength"],
                        thermocline_depth_m=tc["depth_m"],
                        thermocline_recommended_depth_m=tc["recommended_depth_m"],
                        thermocline_advice=tc["advice"] or None,
                        best_hours=bh,
                        stale=stale,
                        factors=factors,
                    )
                )
        return ForecastResponse(
            generated_at=utcnow(),
            last_updated_at=last_updated_at,
            water_level_m=water_level.latest_level_m if water_level else None,
            water_level_trend_7d_m=water_level.trend_7d_m if water_level else 0.0,
            water_level_source=water_level.source if water_level else None,
            water_level_is_fresh=water_level.is_fresh if water_level else False,
            zone=zone_profile["code"],
            zone_label=zone_profile["label"],
            days=days,
        )

    def create_catch(self, payload: CatchCreate, user_id: str) -> CatchRecord:
        caught_at = payload.caught_at or utcnow()
        linked_snapshot = self._nearest_snapshot(caught_at.date())
        record = CatchRecord(
            id=uuid4().hex,
            user_id=user_id,
            species=payload.species,
            score=payload.score,
            latitude=payload.latitude,
            longitude=payload.longitude,
            note=payload.note,
            caught_at=caught_at.astimezone(UTC),
            linked_weather_date=linked_snapshot.day,
            linked_air_temp_c=linked_snapshot.air_temp_c,
            linked_pressure_hpa=linked_snapshot.pressure_hpa,
            linked_water_temp_c=linked_snapshot.water_temp_c,
            linked_wind_speed_m_s=linked_snapshot.wind_speed_m_s,
            linked_wind_direction_deg=linked_snapshot.wind_direction_deg,
            linked_moon_phase=linked_snapshot.moon_phase,
            linked_cloud_cover_pct=linked_snapshot.cloud_cover_pct,
            linked_precipitation_mm=linked_snapshot.precipitation_mm,
            linked_humidity_pct=linked_snapshot.humidity_pct,
            linked_pressure_trend_24h_hpa=linked_snapshot.pressure_trend_24h_hpa,
            linked_daylight_hours=linked_snapshot.daylight_hours,
            created_at=utcnow(),
        )
        return self._catch_repository.save(record)

    def _nearest_snapshot(self, target_day: date) -> WeatherSnapshot:
        snapshots: list[WeatherSnapshot] = []
        if self._historical_snapshot_loader is not None:
            snapshots = self._historical_snapshot_loader(target_day)
        if not snapshots:
            snapshots = self._daily_snapshots()
        return min(snapshots, key=lambda snap: abs((snap.day - target_day).days))

    def _daily_snapshots(self) -> list[WeatherSnapshot]:
        today = datetime.now(UTC).date()
        snapshots: list[WeatherSnapshot] = []
        prev_pressure: float | None = None
        for offset in range(7):
            current_day = today + timedelta(days=offset)
            seasonal = math.sin((current_day.timetuple().tm_yday / 365) * 2 * math.pi)
            moon_phase = ((current_day.toordinal() % 29.53) / 29.53)
            air_temp = round(9 + seasonal * 8 + offset * 0.2, 1)
            pressure = round(1008 + math.cos(offset / 2) * 6, 1)
            water_temp = round(6 + seasonal * 4 + offset * 0.15, 1)
            wind_speed = round(2.0 + abs(math.sin(offset + seasonal)) * 5.0, 1)
            wind_direction = round((210 + offset * 18) % 360, 1)
            cloud_cover = round(40 + math.sin(offset * 1.3) * 30, 1)
            precipitation = round(max(0.0, math.sin(offset * 0.9) * 2.0), 1)
            humidity = round(60 + math.cos(offset * 0.7) * 20, 1)
            trend_24h = round((pressure - prev_pressure) if prev_pressure is not None else 0.0, 1)
            prev_pressure = pressure
            daylight = self._daylight_estimate(current_day)
            snapshots.append(
                WeatherSnapshot(
                    day=current_day,
                    air_temp_c=air_temp,
                    pressure_hpa=pressure,
                    water_temp_c=water_temp,
                    wind_speed_m_s=wind_speed,
                    wind_direction_deg=wind_direction,
                    moon_phase=round(moon_phase, 2),
                    cloud_cover_pct=max(0.0, min(100.0, cloud_cover)),
                    precipitation_mm=precipitation,
                    humidity_pct=max(0.0, min(100.0, humidity)),
                    pressure_trend_6h_hpa=round(trend_24h / 4, 2),
                    pressure_trend_24h_hpa=trend_24h,
                    daylight_hours=daylight,
                )
            )
        return snapshots

    def _daylight_estimate(self, day: date) -> float:
        # Simple astronomical approximation for latitude ~55.99N (Krasnoyarsk reservoir).
        lat = 55.99
        doy = day.timetuple().tm_yday
        decl = 23.44 * math.sin(math.radians((360 / 365) * (doy - 81)))
        cos_h = -math.tan(math.radians(lat)) * math.tan(math.radians(decl))
        cos_h = max(-1.0, min(1.0, cos_h))
        hours = (2 * math.degrees(math.acos(cos_h))) / 15
        return round(hours, 2)

    def default_snapshots(self) -> list[WeatherSnapshot]:
        return self._daily_snapshots()

    def score_species(self, species: FishSpecies, snapshot: WeatherSnapshot, bias: float = 0.0) -> tuple[float, float]:
        score, confidence, _ = self._score_with_factors(species, snapshot, bias=bias)
        return score, confidence

    def _score_species(self, species: FishSpecies, snapshot: WeatherSnapshot, bias: float = 0.0) -> tuple[float, float]:
        return self.score_species(species, snapshot, bias=bias)

    def _score_with_factors(
        self,
        species: FishSpecies,
        snapshot: WeatherSnapshot,
        bias: float = 0.0,
        water_level: WaterLevelContext | None = None,
        zone: dict | None = None,
    ) -> tuple[float, float, list[ScoreFactor]]:
        profile = self._region_profile(species)
        species_profile = self._species_profile(species)
        zone = zone or self._zone_profile(None)
        factors: list[ScoreFactor] = []

        # Zone-adjusted water temperature: same atmospheric snapshot but
        # different zones have different in-situ water temps due to depth,
        # current, and dam discharge effects.
        zone_water_temp = snapshot.water_temp_c + zone["water_temp_offset_c"]

        score = species_profile["base"]
        factors.append(ScoreFactor(name="base", contribution=round(species_profile["base"], 3)))

        # Zone-specific species bias (habitat suitability).
        zone_bias = zone["species_base_bias"].get(species, 0.0)
        if zone_bias != 0.0 and zone.get("code"):
            score += zone_bias
            factors.append(
                ScoreFactor(
                    name="zone_bias",
                    contribution=round(zone_bias, 3),
                    detail=f"{zone['label']} habitat for {species}",
                )
            )

        water_delta = abs(zone_water_temp - species_profile["water_temp_optimal"])
        water_contrib = max(
            -species_profile["water_temp_weight"],
            (species_profile["water_temp_tolerance"] - water_delta) * species_profile["water_temp_weight"] / species_profile["water_temp_tolerance"],
        )
        score += water_contrib
        zone_temp_note = (
            f" (zone Δ{zone['water_temp_offset_c']:+.1f}°C)"
            if zone["water_temp_offset_c"] != 0
            else ""
        )
        factors.append(
            ScoreFactor(
                name="water_temp",
                contribution=round(water_contrib, 3),
                detail=(
                    f"{zone_water_temp:.1f}°C{zone_temp_note} "
                    f"(opt {species_profile['water_temp_optimal']:.0f}°C)"
                ),
            )
        )

        # Pressure scoring runs on SURFACE pressure (real atmospheric pressure
        # at the water edge), not MSL. Open-Meteo returns MSL by default —
        # convert here using region elevation. Fish reacts to absolute
        # pressure in its environment, and the optimum shifts ~3 hPa per
        # 25 m of elevation. Profile optima are stored in surface hPa.
        surface_pressure = self._surface_pressure_hpa(snapshot.air_temp_c, snapshot.pressure_hpa)
        pressure_delta = abs(surface_pressure - species_profile["pressure_optimal"])
        pressure_contrib = max(
            -species_profile["pressure_weight"],
            (8.0 - pressure_delta) * species_profile["pressure_weight"] / 8.0,
        )
        score += pressure_contrib
        factors.append(
            ScoreFactor(
                name="pressure",
                contribution=round(pressure_contrib, 3),
                detail=(
                    f"{snapshot.pressure_hpa:.0f} hPa MSL → "
                    f"{surface_pressure:.0f} hPa surface@{self._region_elevation_m:.0f}m"
                ),
            )
        )

        trend_pref = species_profile["pressure_trend_preference"]
        trend_contrib = self._pressure_trend_factor(
            snapshot.pressure_trend_24h_hpa,
            preference=trend_pref,
            weight=species_profile["pressure_trend_weight"],
        )
        score += trend_contrib
        factors.append(
            ScoreFactor(
                name="pressure_trend_24h",
                contribution=round(trend_contrib, 3),
                detail=f"{snapshot.pressure_trend_24h_hpa:+.1f} hPa/24h",
            )
        )

        moon_contrib = (0.5 - abs(snapshot.moon_phase - species_profile["moon_preferred"])) * species_profile["moon_weight"]
        score += moon_contrib
        factors.append(
            ScoreFactor(name="moon", contribution=round(moon_contrib, 3), detail=f"phase {snapshot.moon_phase:.2f}"),
        )

        wind_speed_contrib = self._wind_speed_factor(
            snapshot.wind_speed_m_s,
            optimal=profile["wind_optimal"],
            spread=profile["wind_spread"],
            weight=profile["wind_weight"],
        )
        score += wind_speed_contrib
        factors.append(
            ScoreFactor(
                name="wind_speed",
                contribution=round(wind_speed_contrib, 3),
                detail=f"{snapshot.wind_speed_m_s:.1f} m/s",
            )
        )

        wind_dir_contrib = self._wind_direction_factor(
            snapshot.wind_direction_deg,
            preferred_deg=profile["preferred_wind_deg"],
            weight=profile["wind_dir_weight"],
        )
        score += wind_dir_contrib
        factors.append(
            ScoreFactor(
                name="wind_direction",
                contribution=round(wind_dir_contrib, 3),
                detail=f"{snapshot.wind_direction_deg:.0f}°",
            )
        )

        cloud_contrib = self._cloud_factor(
            snapshot.cloud_cover_pct,
            optimal=species_profile["cloud_optimal"],
            weight=species_profile["cloud_weight"],
        )
        score += cloud_contrib
        factors.append(
            ScoreFactor(
                name="cloud_cover",
                contribution=round(cloud_contrib, 3),
                detail=f"{snapshot.cloud_cover_pct:.0f}%",
            )
        )

        precip_contrib = self._precipitation_factor(
            snapshot.precipitation_mm,
            tolerance=species_profile["precipitation_tolerance"],
            weight=species_profile["precipitation_weight"],
        )
        score += precip_contrib
        factors.append(
            ScoreFactor(
                name="precipitation",
                contribution=round(precip_contrib, 3),
                detail=f"{snapshot.precipitation_mm:.1f} mm",
            )
        )

        daylight_contrib = self._daylight_factor(
            snapshot.daylight_hours,
            optimal=species_profile["daylight_optimal"],
            weight=species_profile["daylight_weight"],
        )
        score += daylight_contrib
        factors.append(
            ScoreFactor(
                name="daylight",
                contribution=round(daylight_contrib, 3),
                detail=f"{snapshot.daylight_hours:.1f} h",
            )
        )

        if water_level is not None:
            water_level_contrib = self._water_level_factor(
                level_m=water_level.latest_level_m,
                trend_7d_m=water_level.trend_7d_m,
                species=species,
                day=snapshot.day,
            ) * zone["level_sensitivity"]
            score += water_level_contrib
            sens_note = (
                f", zone ×{zone['level_sensitivity']:.1f}"
                if zone["level_sensitivity"] != 1.0
                else ""
            )
            detail = (
                f"{water_level.latest_level_m:.2f} m, Δ7d {water_level.trend_7d_m:+.2f} m"
                f" ({water_level.source}{sens_note})"
            )
            factors.append(
                ScoreFactor(
                    name="water_level",
                    contribution=round(water_level_contrib, 3),
                    detail=detail,
                )
            )

        regime = self._ice_regime(snapshot, zone=zone)
        ice_contrib = self._ice_regime_factor(regime=regime, day=snapshot.day, species=species)
        if ice_contrib != 0.0 or regime != "open":
            score += ice_contrib
            factors.append(
                ScoreFactor(
                    name="ice_regime",
                    contribution=round(ice_contrib, 3),
                    detail=f"{regime} (Tw={zone_water_temp:.1f}°C)",
                )
            )

        # Use zone-adjusted water temp for thermocline detection too.
        thermocline_contrib = self._thermocline_factor_temp(
            water_temp_c=zone_water_temp, species=species
        )
        if thermocline_contrib != 0.0:
            score += thermocline_contrib
            factors.append(
                ScoreFactor(
                    name="thermocline",
                    contribution=round(thermocline_contrib, 3),
                    detail=f"Tw={zone_water_temp:.1f}°C (warm stratification)",
                )
            )

        season_contrib = self._season_factor(snapshot.day, species=species)
        score += season_contrib
        factors.append(ScoreFactor(name="season", contribution=round(season_contrib, 3)))

        # Species-specific spawning state (per-species temperature trigger,
        # not the calendar-wide ban). Pre-spawn fattening = positive,
        # active spawn = strong negative, post-spawn recovery = mild
        # negative. Module is imported lazily so circular imports don't bite.
        from app.species_spawning import species_spawn_state, species_spawn_factor_contribution
        spawn = species_spawn_state(
            species=species,
            day=snapshot.day,
            water_temp_c=zone_water_temp,
            zone_code=zone.get("code") if zone else None,
        )
        spawn_contrib = species_spawn_factor_contribution(spawn)
        if spawn.phase != "none":
            score += spawn_contrib
            phase_label = {
                "pre": "предспрос (предспрос-жор)",
                "active": "активный нерест",
                "post": "посленерестовое восстановление",
            }[spawn.phase]
            factors.append(
                ScoreFactor(
                    name="species_spawn",
                    contribution=round(spawn_contrib, 3),
                    detail=f"{species}: {phase_label} (Tw={zone_water_temp:.1f}°C)",
                )
            )

        if bias:
            score += bias
            factors.append(ScoreFactor(name="ml_bias", contribution=round(bias, 3)))

        # Multiplicative gates: a single dominant adverse condition can
        # override an otherwise favourable additive score. This captures
        # the fishing-reality fact that lockjaw on a sharp pressure shock
        # is binary, not gradual, even if every other factor is great.
        # Each gate ∈ [0.3, 1.0]; final = additive_score × Π gates.
        # Net effect of each gate is recorded as its own ScoreFactor with
        # contribution = (after × gate) − after, preserving explainability.
        additive_score = max(0.0, score)
        gates = self._collect_gates(species=species, snapshot=snapshot, zone_water_temp=zone_water_temp)
        running = additive_score
        min_gate = 1.0
        for gate_name, gate_value, gate_detail in gates:
            after = running * gate_value
            net = after - running
            if abs(net) >= 0.001:
                factors.append(
                    ScoreFactor(
                        name=gate_name,
                        contribution=round(net, 3),
                        detail=f"{gate_detail} (×{gate_value:.2f})",
                    )
                )
            running = after
            min_gate = min(min_gate, gate_value)

        normalized_score = max(0.0, min(5.0, round(running, 2)))
        # Strong gates also reduce confidence — predictions near regime
        # transitions are inherently uncertain.
        confidence_dampening = 0.5 + 0.5 * min_gate
        normalized_confidence = max(
            0.0, min(1.0, round(species_profile["confidence"] * confidence_dampening, 2))
        )
        return normalized_score, normalized_confidence, factors

    def _collect_gates(
        self,
        *,
        species: FishSpecies,
        snapshot: WeatherSnapshot,
        zone_water_temp: float | None = None,
    ) -> list[tuple[str, float, str]]:
        """Compute multiplicative dampeners. Each entry: (name, value, detail).

        Order matters only for explainability — the math is commutative.
        Gates that evaluate to ~1.0 are still emitted only if there's a
        meaningful explanation worth showing the user.
        """
        gates: list[tuple[str, float, str]] = []

        shock = self._pressure_shock_gate(snapshot.pressure_trend_24h_hpa, species=species)
        if shock < 0.99:
            direction = "sharp rise" if snapshot.pressure_trend_24h_hpa > 0 else "sharp drop"
            gates.append((
                "pressure_shock_gate",
                shock,
                f"ΔP24h={snapshot.pressure_trend_24h_hpa:+.1f} hPa ({direction})",
            ))

        severe = self._severe_weather_gate(snapshot)
        if severe < 0.99:
            gates.append((
                "severe_weather_gate",
                severe,
                f"wind {snapshot.wind_speed_m_s:.1f} m/s + {snapshot.precipitation_mm:.1f} mm",
            ))

        tw = zone_water_temp if zone_water_temp is not None else snapshot.water_temp_c
        thermal = self._thermal_shock_gate(tw, species=species)
        if thermal < 0.99:
            kind = self._thermal_shock_kind(tw, species=species)
            gates.append((
                "thermal_shock_gate",
                thermal,
                f"Tw={tw:.1f}°C ({kind})",
            ))

        return gates

    def _pressure_shock_gate(self, trend_24h: float, *, species: FishSpecies) -> float:
        """Sharp pressure swing dampens activity regardless of other factors.

        Folklore-validated: |ΔP/24h| ≥ 5 hPa is a noticeable lockjaw
        trigger; 8+ hPa is a near-shutdown for 1-2 days. Cyprinids (bream)
        and percids (perch) are more sensitive than predators (pike).
        Returns multiplier in [0.30, 1.0].
        """
        magnitude = abs(trend_24h)
        if magnitude < 3.0:
            return 1.0
        # Linear ramp from 3 hPa (gate=1.0) to 12 hPa (gate=floor).
        floor_by_species = {"pike": 0.45, "perch": 0.35, "bream": 0.30}
        floor = floor_by_species.get(species, 0.35)
        ramp = max(0.0, min(1.0, (magnitude - 3.0) / 9.0))
        return 1.0 - (1.0 - floor) * ramp

    def _severe_weather_gate(self, snapshot: WeatherSnapshot) -> float:
        """Gale + heavy precipitation: combined effect renders the lake
        unfishable for shore/small-boat anglers AND mixes the water column,
        which all species dislike. Returns multiplier in [0.40, 1.0].
        """
        wind_excess = max(0.0, snapshot.wind_speed_m_s - 10.0)  # over Beaufort 5
        precip_excess = max(0.0, snapshot.precipitation_mm - 8.0)
        if wind_excess <= 0.0 and precip_excess <= 0.0:
            return 1.0
        intensity = min(1.0, wind_excess / 10.0 + precip_excess / 15.0)
        return 1.0 - 0.6 * intensity

    def _thermal_shock_kind(self, water_temp_c: float, *, species: FishSpecies) -> str:
        if species == "bream":
            return "below feeding threshold"
        if species == "pike":
            return "near-lockjaw cold"
        return "heat-stressed"

    def _thermal_shock_gate(self, water_temp_c: float, *, species: FishSpecies) -> float:
        """Below-feeding-threshold water temperature is near-binary for
        cyprinids: bream simply does not eat below ~6-7°C, regardless of
        pressure, moon, etc. Pike has its own cold floor near 1°C
        (lockjaw under deep ice). Perch is broadly tolerant.
        Returns multiplier in [0.35, 1.0].
        """
        if species == "bream":
            if water_temp_c >= 8.0:
                return 1.0
            if water_temp_c <= 4.0:
                return 0.35
            # 4..8°C ramp
            return 0.35 + (water_temp_c - 4.0) / 4.0 * 0.65
        if species == "pike":
            if water_temp_c >= 2.0:
                return 1.0
            if water_temp_c <= 0.0:
                return 0.55
            return 0.55 + water_temp_c / 2.0 * 0.45
        # perch — almost no thermal shock; only extreme heat matters
        if water_temp_c >= 26.0:
            return 0.6
        if water_temp_c >= 24.0:
            return 0.8
        return 1.0

    def _cloud_factor(self, cloud_pct: float, *, optimal: float, weight: float) -> float:
        delta = abs(cloud_pct - optimal) / 100.0
        return (1.0 - delta * 2.0) * weight

    def _precipitation_factor(self, precip_mm: float, *, tolerance: float, weight: float) -> float:
        if precip_mm <= tolerance:
            return 0.0
        excess = min(precip_mm - tolerance, 15.0)
        return -weight * (excess / 15.0)

    def _daylight_factor(self, hours: float, *, optimal: float, weight: float) -> float:
        delta = abs(hours - optimal)
        return max(-weight, (3.0 - delta) * weight / 3.0)

    def _zone_profile(self, zone: str | None) -> dict:
        """Krasnoyarsk reservoir bay-based zoning.

        Krasnoyarsk anglers navigate by named bays, not abstract regions.
        The dam at Divnogorsk is the reservoir's northern boundary —
        whatever lies downstream of it is the Yenisei river (out of scope).

        Each bay carries a passport derived from its formative river,
        bank type, depth class and thermal behaviour. The same atmospheric
        snapshot is therefore interpreted differently per bay.
        """
        if self._region != "krasnoyarsk" or zone is None:
            return _BASELINE_ZONE_PROFILE
        return _BAY_REGISTRY.get(zone, _BASELINE_ZONE_PROFILE)

    def _surface_pressure_hpa(self, air_temp_c: float, msl_hpa: float) -> float:
        """Convert mean-sea-level pressure to actual surface pressure at the
        configured region elevation.

        Uses the international barometric formula (ISA, troposphere):
            P_surface = MSL * (1 - L*h / (T + L*h)) ** 5.255
        where L = 0.0065 K/m (lapse rate) and T is air temperature at the
        surface in Kelvin. For Krasnoyarsk reservoir (h≈234 m), this yields
        roughly -27 hPa relative to MSL.

        air_temp_c is the air temperature at the surface; used to keep the
        seasonal swing in the conversion physically accurate (cold air =
        slightly larger MSL→surface delta).
        """
        h = max(0.0, self._region_elevation_m)
        if h <= 0.5:
            return msl_hpa
        T = air_temp_c + 273.15
        return msl_hpa * (1.0 - (0.0065 * h) / (T + 0.0065 * h)) ** 5.255

    def _water_level_factor(
        self,
        *,
        level_m: float,
        trend_7d_m: float,
        species: FishSpecies,
        day: date | None = None,
    ) -> float:
        """Species-specific reservoir level factor.

        Krasnoyarsk reservoir: NPU=243.0 m (summer full), UMO=225.0 m (late-winter).
        Heuristics based on fishing reports for the reservoir:
        - Bream: strong preference for stable / slowly rising levels. Falling
          levels in early spring (drawdown) scatter schools.
        - Pike: positive signal on rising levels (fish hunt into flooded
          shallows); mild negative on sustained fall.
        - Perch: relatively insensitive; slight penalty on rapid change.

        Regional modifier (Krasnoyarsk): spring drawdown (Mar-May) is a normal
        seasonal pattern — fish is acclimated, so the penalty for a negative
        trend in those months is softened. Conversely, sustained drop in
        summer (Jul-Aug) when fill is expected is a genuine red flag.
        """
        is_krasnoyarsk = self._region == "krasnoyarsk"
        is_spring_drawdown = (
            is_krasnoyarsk and day is not None and day.month in {3, 4, 5} and trend_7d_m < 0
        )
        is_summer_anomaly_drop = (
            is_krasnoyarsk and day is not None and day.month in {7, 8} and trend_7d_m < -0.3
        )
        trend_effective = trend_7d_m
        if is_spring_drawdown:
            trend_effective = trend_7d_m * 0.4  # normal seasonal behaviour

        if species == "bream":
            if is_summer_anomaly_drop:
                return -0.45  # summer drop is unusual and stressful
            if trend_effective <= -0.3:
                return max(-0.35, trend_effective * 0.6)
            if abs(trend_effective) <= 0.15:
                return 0.2  # stable = feeding
            if trend_effective >= 0.3:
                return 0.1  # slow rise is fine
            return 0.0
        if species == "pike":
            if trend_effective >= 0.2:
                return min(0.25, trend_effective * 0.5)
            if trend_effective <= -0.4:
                return max(-0.2, trend_effective * 0.3)
            return 0.05
        # perch
        if abs(trend_effective) >= 0.5:
            return -0.1
        return 0.05

    def _ice_regime(self, snapshot: "WeatherSnapshot", *, zone: dict | None = None) -> str:
        """Classify open/transition/ice regime for Eastern Siberia.

        Uses water temperature + calendar to decide. Each zone passes its
        own freeze/thaw thresholds and ice/transition month windows so the
        upper reach (long ice season) and lower polynya (short ice season)
        are handled differently from the middle baseline.
        """
        month = snapshot.day.month
        zone_water_temp = snapshot.water_temp_c + (zone["water_temp_offset_c"] if zone else 0.0)

        if self._region != "krasnoyarsk":
            # Middle-band / northwest: short ice window, less dramatic
            if zone_water_temp <= 1.0 and month in {12, 1, 2, 3}:
                return "ice"
            if zone_water_temp <= 4.0 and month in {11, 12, 3, 4}:
                return "transition"
            return "open"

        # Krasnoyarsk: use zone-specific thresholds and month windows.
        zp = zone or self._zone_profile(None)
        if zone_water_temp <= zp["ice_freeze_temp_c"] and month in zp["ice_months"]:
            return "ice"
        if zone_water_temp <= zp["ice_thaw_temp_c"] and month in zp["transition_months"]:
            return "transition"
        return "open"

    def _ice_regime_factor(self, *, regime: str, day: date, species: FishSpecies) -> float:
        """Regime-based adjustment. Currently tuned for Krasnoyarsk.

        Ice fishing reality:
        - Perch is the primary ice target; first ice (Nov-Dec) and last ice
          (late Mar-Apr) are peaks, deep winter (Jan-Feb) has midday-only bite.
        - Pike under ice is sluggish except at last ice (pre-spawn).
        - Bream is near-dormant under ice on Krasnoyarsk reservoir.
        Transition (ice-out / freeze-up) is unstable — pike post-ice aggressive,
        bream still cold.
        """
        if self._region != "krasnoyarsk":
            # Other regions: small effect only
            if regime == "ice":
                if species == "perch":
                    return 0.15
                if species == "bream":
                    return -0.35
                return -0.15
            return 0.0

        month = day.month
        if regime == "ice":
            if species == "perch":
                # first ice / last ice are prime; deep winter still OK midday
                if month in {11, 12, 3, 4}:
                    return 0.3
                return 0.1
            if species == "pike":
                if month in {3, 4}:
                    return 0.18  # last ice pre-spawn activity
                return -0.28  # deep winter lock-jaw
            # bream
            return -0.6
        if regime == "transition":
            if species == "pike":
                return 0.22  # post-ice aggression
            if species == "bream":
                return -0.22  # still too cold
            return 0.08
        return 0.0

    def best_hours(self, snapshot: "WeatherSnapshot") -> list[dict]:
        """Compute the best fishing-hour windows for a single forecast day.

        Always returns dawn/dusk windows (±1h around sunrise/sunset) when
        the snapshot has those times. Adds real solunar major and minor
        windows from a lunar ephemeris (PyEphem) — upper/lower transits
        and moon rise/set at the configured fishing location. Each
        lunar window's intensity is scaled by an illumination-derived
        quality multiplier so that quarter-moon windows are visibly
        weaker than full/new-moon ones.

        Output: list[dict] of {start, end, label, kind, intensity}, all
        UTC datetimes (frontend renders in local time). Windows may
        overlap; the UI stacks them.
        """
        out: list[dict] = []
        sr = snapshot.sunrise
        ss = snapshot.sunset
        if sr is not None and ss is not None:
            out.append({
                "start": sr - timedelta(hours=1),
                "end": sr + timedelta(hours=1),
                "label": "Утренняя зорька",
                "kind": "dawn",
                "intensity": 1.0,
            })
            out.append({
                "start": ss - timedelta(hours=1),
                "end": ss + timedelta(hours=1),
                "label": "Вечерняя зорька",
                "kind": "dusk",
                "intensity": 1.0,
            })

        # Real solunar windows from ephemeris.
        try:
            from app.solunar import compute_solunar_periods
            sol = compute_solunar_periods(
                target_date=snapshot.day,
                lat=self._location_lat,
                lon=self._location_lon,
            )
            quality = sol.get("quality", 0.5)
            # Major: dimmer at quarters (0.4 floor) so the strip still
            # shows them, but they're visually distinguishable from
            # near-syzygy peaks.
            for w in sol.get("major", []):
                out.append({
                    **w,
                    "kind": "lunar_major",
                    "intensity": round(max(0.4, 0.4 + 0.6 * quality), 2),
                })
            for w in sol.get("minor", []):
                out.append({
                    **w,
                    "kind": "lunar_minor",
                    "intensity": round(max(0.3, 0.3 + 0.4 * quality), 2),
                })
        except ImportError:
            # ephem missing — fall back to dawn/dusk only.
            pass
        except Exception:
            # Don't poison the forecast on any ephemeris glitch.
            pass

        out.sort(key=lambda w: w["start"])
        return out

    def thermocline_advisory(
        self,
        *,
        water_temp_c: float,
        zone: dict | None,
        recent_wind_speeds_m_s: list[float] | None = None,
    ) -> dict:
        """Estimate thermocline depth, strength, and recommended fishing depth.

        Inputs come from already-zone-adjusted water temp + the zone profile
        (specifically its archetype, which encodes typical depth structure).

        ``recent_wind_speeds_m_s`` (optional): daily-mean wind speeds for
        the past 2–3 days. Strong sustained wind (≥8 m/s average) mixes
        the upper 5–7 m of the column and breaks the thermocline; we
        scale strength down accordingly. None = ignore mixing (default).

        Returns a dict with:
          * strength: 0 (no stratification) → 1 (sharp summer thermocline).
            Built from temperature delta vs. hypolimnion baseline (~6°C)
            and dampened by archetype's stratification capacity.
          * depth_m: predicted depth of the thermal cliff in metres
            (None for shallow archetypes where the column mixes top-to-bottom).
          * recommended_depth_m: where bait should sit. Just above the
            thermocline boundary (predator territory) for stratified zones,
            or "по дну" cue for shallow zones.
          * advice: short Russian-language hint for the UI.

        This is purely predictive (no observed profile data). Real
        measurements come from /v1/water-temp-readings (user-submitted)
        and will eventually train a regression model that replaces these
        heuristics. For now: simple, transparent, and usable.
        """
        if self._region != "krasnoyarsk" or zone is None or not zone.get("archetype"):
            return {"strength": 0.0, "depth_m": None, "recommended_depth_m": None, "advice": ""}

        archetype = zone["archetype"]

        # Zone-specific stratification capacity (1.0 = strong, 0.0 = none).
        # Reflects depth + exposure: shallow swampy bays mix completely at
        # the slightest wind; deep open channel holds a sharp thermocline.
        strat_capacity = {
            "shallow_warm": 0.30,
            "swampy_shallow": 0.20,
            "narrow_shallow": 0.40,
            "medium_balanced": 0.70,
            "irregular_mixed": 0.65,
            "steep_cool": 0.85,
            "rocky_deep_cool": 0.90,
            "deep_cold": 1.00,
            "main_channel": 1.00,
        }.get(archetype, 0.70)

        # Temperature gradient strength: surface warm enough relative to
        # hypolimnion (~6°C). Below 12°C no meaningful stratification.
        if water_temp_c < 12.0:
            temp_strength = 0.0
        else:
            temp_strength = min(1.0, (water_temp_c - 12.0) / 10.0)  # 0 at 12, 1 at 22

        # Wind-mixing modifier. Sustained ≥8 m/s wind for 2+ days
        # disrupts the upper layer and erodes the cliff. We use the
        # mean of provided recent winds, which the caller fills with
        # daily averages from past Open-Meteo snapshots (typically the
        # 2–3 days preceding the forecast day).
        wind_mix = 1.0
        if recent_wind_speeds_m_s:
            avg_wind = sum(recent_wind_speeds_m_s) / len(recent_wind_speeds_m_s)
            if avg_wind >= 8.0:
                # Linear ramp: 8 m/s → ×0.5, 12+ m/s → ×0.2 (almost no
                # stratification holds together after a multi-day gale).
                excess = min(1.0, (avg_wind - 8.0) / 4.0)
                wind_mix = 0.5 - 0.3 * excess  # 0.5 at 8 m/s, 0.2 at 12+

        strength = round(temp_strength * strat_capacity * wind_mix, 2)

        # Approximate thermocline depth (m). Heuristic:
        # depth ≈ base_depth_for_archetype × (1 - 0.5 × wind_capacity_inverse)
        # but for v1 we just use a per-archetype constant scaled by surface
        # temp (warmer surface → slightly deeper thermocline as the warm
        # layer grows over the season).
        if strength < 0.15:
            depth_m = None
            recommended_depth_m = None
        else:
            base_depth = {
                "shallow_warm": 4,
                "swampy_shallow": 3,
                "narrow_shallow": 5,
                "medium_balanced": 7,
                "irregular_mixed": 7,
                "steep_cool": 9,
                "rocky_deep_cool": 10,
                "deep_cold": 12,
                "main_channel": 14,
            }.get(archetype, 8)
            seasonal_grow = max(0, int((water_temp_c - 14) * 0.4))  # +1 m per 2.5°C above 14
            depth_m = base_depth + seasonal_grow
            # Recommended bait placement: 1–2 m above the thermal cliff
            # (predator stages on the cooler side and ambushes upward).
            recommended_depth_m = max(2, depth_m - 2)

        # UI-facing advice text.
        if strength < 0.15:
            advice = "Вода перемешана — ловите по рельефу дна."
        elif strength < 0.4:
            advice = (
                f"Слабая стратификация (~{depth_m} м). Рыба распределена по столбу, "
                "пробуйте разные горизонты."
            )
        elif strength < 0.7:
            advice = (
                f"Умеренный термоклин ~{depth_m} м. Хищник у нижней кромки, "
                f"ставьте приманку на {recommended_depth_m}–{depth_m} м."
            )
        else:
            advice = (
                f"Плотный термоклин ~{depth_m} м. Поверхностная ловля бесполезна. "
                f"Троллинг/отвес на {recommended_depth_m}–{depth_m} м, бровки и свалы."
            )

        return {
            "strength": strength,
            "depth_m": depth_m,
            "recommended_depth_m": recommended_depth_m,
            "advice": advice,
        }

    def _thermocline_factor(self, *, snapshot: "WeatherSnapshot", species: FishSpecies) -> float:
        return self._thermocline_factor_temp(water_temp_c=snapshot.water_temp_c, species=species)

    def _thermocline_factor_temp(self, *, water_temp_c: float, species: FishSpecies) -> float:
        """Summer stratification penalty for Krasnoyarsk.

        When reservoir surface exceeds ~20°C a pronounced thermocline forms
        and fish retreats to depth, making bank/trolling bite harder. Pike
        is most affected; bream less so; perch only marginally.

        Takes water temperature directly so callers can pass zone-adjusted
        Tw (upper zone is warmer, lower zone is cooler than baseline).
        """
        if self._region != "krasnoyarsk":
            return 0.0
        if water_temp_c < 20.0:
            return 0.0
        excess = min(water_temp_c - 20.0, 6.0) / 6.0
        if species == "pike":
            return -0.25 * excess
        if species == "bream":
            return -0.1 * excess
        return -0.05 * excess

    def _pressure_trend_factor(self, trend_hpa: float, *, preference: float, weight: float) -> float:
        # preference: -1 prefer falling, 0 prefer stable, +1 prefer rising
        if preference == 0:
            return max(-weight, weight * (1.0 - min(abs(trend_hpa), 6.0) / 6.0))
        aligned = trend_hpa * preference
        return max(-weight, min(weight, aligned * weight / 5.0))

    def _wind_speed_factor(self, wind_speed_m_s: float, *, optimal: float, spread: float, weight: float) -> float:
        # Peak around optimal wind speed, smoother decay around it.
        return max(-weight, min(weight, (spread - abs(wind_speed_m_s - optimal)) * (weight / spread)))

    def _wind_direction_factor(self, wind_direction_deg: float, *, preferred_deg: float, weight: float) -> float:
        # Direction bonus based on angular distance to preferred bearing.
        delta = abs((wind_direction_deg - preferred_deg + 180) % 360 - 180)
        return (1.0 - (delta / 180.0)) * weight - (weight / 2.0)

    def _season_factor(self, day: date, *, species: FishSpecies) -> float:
        if self._region == "krasnoyarsk":
            return self._season_factor_krasnoyarsk(day, species=species)
        if self._region == "northwest":
            return self._season_factor_northwest(day, species=species)
        return self._season_factor_default(day, species=species)

    def _season_factor_krasnoyarsk(self, day: date, *, species: FishSpecies) -> float:
        """Eastern Siberia seasonal calendar.

        Shorter warm season than European Russia (ice-out mid-May,
        freeze-up mid-November). Pike spawns late (May, after ice-out).
        Bream has a compressed 3-4 month active window. Perch works
        year-round including ice.
        """
        month = day.month
        if species == "pike":
            if month in {5, 9, 10}:
                return 0.3  # ice-out burst + autumn feed-up
            if month == 6:
                return 0.18
            if month == 4:
                return 0.08  # late-ice, transition
            if month in {7, 8}:
                return -0.15  # summer thermocline slump
            if month == 11:
                return 0.0  # freeze-up
            return -0.2  # deep winter under ice
        if species == "bream":
            if month in {6, 7, 8}:
                return 0.32
            if month == 9:
                return 0.2
            if month == 5:
                return 0.08  # only after reliable warm-up
            if month == 10:
                return -0.12
            if month == 4:
                return -0.3  # still too cold / under ice
            return -0.4  # winter dormancy
        # perch — winter-capable
        if month in {6, 7, 8}:
            return 0.22
        if month in {5, 9}:
            return 0.24  # pre-spawn spring / autumn feed-up are both prime
        if month in {10, 11}:
            return 0.15  # first ice
        if month in {3, 4}:
            return 0.18  # last ice
        return 0.02  # deep winter

    def _season_factor_northwest(self, day: date, *, species: FishSpecies) -> float:
        month = day.month
        if species == "pike":
            if month in {4, 5, 6, 9}:
                return 0.24
            if month in {7, 8}:
                return -0.06
            return -0.02
        if species == "bream":
            if month in {6, 7, 8}:
                return 0.26
            if month in {5, 9}:
                return 0.14
            return -0.18
        if month in {5, 6, 7, 8}:
            return 0.18
        if month in {9, 10}:
            return 0.07
        return -0.04

    def _season_factor_default(self, day: date, *, species: FishSpecies) -> float:
        month = day.month
        if species == "pike":
            if month in {4, 5, 6, 9, 10}:
                return 0.24
            if month in {7, 8}:
                return -0.08
            return -0.03
        if species == "bream":
            if month in {5, 6, 7, 8}:
                return 0.24
            if month in {9}:
                return 0.1
            return -0.18
        if month in {5, 6, 7, 8, 9}:
            return 0.2
        if month in {10, 11}:
            return 0.05
        return -0.05

    def _region_profile(self, species: FishSpecies) -> dict[str, float]:
        if self._region == "krasnoyarsk":
            if species == "pike":
                return {
                    "preferred_wind_deg": 230.0,
                    "wind_optimal": 4.8,
                    "wind_spread": 4.2,
                    "wind_weight": 0.42,
                    "wind_dir_weight": 0.36,
                }
            if species == "bream":
                return {
                    "preferred_wind_deg": 195.0,
                    "wind_optimal": 2.4,
                    "wind_spread": 3.0,
                    "wind_weight": 0.3,
                    "wind_dir_weight": 0.22,
                }
            return {
                "preferred_wind_deg": 165.0,
                "wind_optimal": 3.6,
                "wind_spread": 3.8,
                "wind_weight": 0.34,
                "wind_dir_weight": 0.3,
            }

        if self._region == "northwest":
            if species == "pike":
                return {
                    "preferred_wind_deg": 245.0,
                    "wind_optimal": 4.2,
                    "wind_spread": 4.0,
                    "wind_weight": 0.4,
                    "wind_dir_weight": 0.33,
                }
            if species == "bream":
                return {
                    "preferred_wind_deg": 200.0,
                    "wind_optimal": 2.2,
                    "wind_spread": 2.8,
                    "wind_weight": 0.28,
                    "wind_dir_weight": 0.2,
                }
            return {
                "preferred_wind_deg": 180.0,
                "wind_optimal": 3.1,
                "wind_spread": 3.5,
                "wind_weight": 0.3,
                "wind_dir_weight": 0.27,
            }

        if species == "pike":
            return {
                "preferred_wind_deg": 240.0,
                "wind_optimal": 4.5,
                "wind_spread": 4.0,
                "wind_weight": 0.4,
                "wind_dir_weight": 0.35,
            }
        if species == "bream":
            return {
                "preferred_wind_deg": 200.0,
                "wind_optimal": 2.3,
                "wind_spread": 3.0,
                "wind_weight": 0.28,
                "wind_dir_weight": 0.22,
            }
        return {
            "preferred_wind_deg": 170.0,
            "wind_optimal": 3.2,
            "wind_spread": 3.5,
            "wind_weight": 0.32,
            "wind_dir_weight": 0.28,
        }

    def _species_profile(self, species: FishSpecies) -> dict[str, float]:
        if self._region == "krasnoyarsk":
            return self._species_profile_krasnoyarsk(species)
        return self._species_profile_default(species)

    def _species_profile_krasnoyarsk(self, species: FishSpecies) -> dict[str, float]:
        """Eastern Siberia tuning: colder optima, surface-pressure scoring.

        Key differences from middle-band Russia:
        - Pike: prefers 8-12°C (Siberian populations are cold-adapted).
        - Bream: needs reliable 15°C+ to actively feed (peak 18-20°C). Reservoir
          rarely exceeds 22°C even at peak summer, so optimum is set slightly
          lower but drop-off below optimum is sharper (narrower tolerance).
        - Perch: very broad thermal range including under-ice, so tolerance
          extends to 13-14°C spread.

        Pressure optima are expressed in SURFACE hPa at the reservoir water
        edge (median elevation 234 m AMSL). At that height MSL pressure is
        ~27 hPa higher than surface, so a "good fishing" surface reading of
        ~987 hPa corresponds to MSL ~1014 hPa — matching the canonical
        750 mmHg fisherman's-barometer rule applied at high altitude.
        """
        if species == "pike":
            return {
                "base": 2.8,
                "water_temp_optimal": 10.0,
                "water_temp_tolerance": 8.0,
                "water_temp_weight": 1.0,
                "pressure_optimal": 986.0,  # surface hPa (≈1014 MSL @ 234m)
                "pressure_weight": 0.35,
                "pressure_trend_preference": -0.6,
                "pressure_trend_weight": 0.35,
                "moon_preferred": 0.5,
                "moon_weight": 0.6,
                "cloud_optimal": 70.0,
                "cloud_weight": 0.3,
                "precipitation_tolerance": 3.0,
                "precipitation_weight": 0.25,
                "daylight_optimal": 13.0,
                "daylight_weight": 0.2,
                "confidence": 0.72,
            }
        if species == "bream":
            return {
                "base": 2.4,
                "water_temp_optimal": 19.0,
                "water_temp_tolerance": 7.5,  # sharper drop-off in cold
                "water_temp_weight": 1.2,
                "pressure_optimal": 988.0,  # surface hPa (≈1016 MSL @ 234m)
                "pressure_weight": 0.4,
                "pressure_trend_preference": 0.0,
                "pressure_trend_weight": 0.4,
                "moon_preferred": 0.8,
                "moon_weight": 0.5,
                "cloud_optimal": 55.0,
                "cloud_weight": 0.25,
                "precipitation_tolerance": 1.0,
                "precipitation_weight": 0.35,
                "daylight_optimal": 16.0,  # long Siberian summer days
                "daylight_weight": 0.3,
                "confidence": 0.66,
            }
        return {
            "base": 2.5,
            "water_temp_optimal": 13.0,
            "water_temp_tolerance": 13.0,  # very broad incl. ice fishing
            "water_temp_weight": 0.9,
            "pressure_optimal": 988.0,  # surface hPa (≈1016 MSL @ 234m)
            "pressure_weight": 0.3,
            "pressure_trend_preference": 0.0,
            "pressure_trend_weight": 0.3,
            "moon_preferred": 0.35,
            "moon_weight": 0.55,
            "cloud_optimal": 40.0,
            "cloud_weight": 0.25,
            "precipitation_tolerance": 2.0,
            "precipitation_weight": 0.3,
            "daylight_optimal": 13.5,
            "daylight_weight": 0.22,
            "confidence": 0.7,  # more ground-truth reports for perch locally
        }

    def _species_profile_default(self, species: FishSpecies) -> dict[str, float]:
        """Generic / middle-band Russia profile.

        Pressure optima expressed in SURFACE hPa at default elevation 150 m
        (typical European-Russia floodplain), so canonical "750 mmHg = good
        fishing" lines up with MSL ~1013 hPa as fishermen know it.
        """
        if species == "pike":
            return {
                "base": 2.8,
                "water_temp_optimal": 12.0,
                "water_temp_tolerance": 9.0,
                "water_temp_weight": 1.0,
                "pressure_optimal": 994.0,  # surface hPa (≈1012 MSL @ 150m)
                "pressure_weight": 0.35,
                "pressure_trend_preference": -0.6,
                "pressure_trend_weight": 0.35,
                "moon_preferred": 0.5,
                "moon_weight": 0.6,
                "cloud_optimal": 70.0,
                "cloud_weight": 0.3,
                "precipitation_tolerance": 3.0,
                "precipitation_weight": 0.25,
                "daylight_optimal": 12.0,
                "daylight_weight": 0.2,
                "confidence": 0.72,
            }
        if species == "bream":
            return {
                "base": 2.4,
                "water_temp_optimal": 20.0,
                "water_temp_tolerance": 10.0,
                "water_temp_weight": 1.1,
                "pressure_optimal": 996.0,  # surface hPa (≈1014 MSL @ 150m)
                "pressure_weight": 0.4,
                "pressure_trend_preference": 0.0,
                "pressure_trend_weight": 0.4,
                "moon_preferred": 0.8,
                "moon_weight": 0.5,
                "cloud_optimal": 55.0,
                "cloud_weight": 0.25,
                "precipitation_tolerance": 1.0,
                "precipitation_weight": 0.35,
                "daylight_optimal": 15.0,
                "daylight_weight": 0.3,
                "confidence": 0.66,
            }
        return {
            "base": 2.5,
            "water_temp_optimal": 15.0,
            "water_temp_tolerance": 9.0,
            "water_temp_weight": 1.0,
            "pressure_optimal": 994.0,  # surface hPa (≈1012 MSL @ 150m)
            "pressure_weight": 0.3,
            "pressure_trend_preference": 0.0,
            "pressure_trend_weight": 0.3,
            "moon_preferred": 0.35,
            "moon_weight": 0.55,
            "cloud_optimal": 40.0,
            "cloud_weight": 0.25,
            "precipitation_tolerance": 2.0,
            "precipitation_weight": 0.3,
            "daylight_optimal": 13.5,
            "daylight_weight": 0.25,
            "confidence": 0.68,
        }
