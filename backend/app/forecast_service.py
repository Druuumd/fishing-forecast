import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Callable
from uuid import uuid4

from app.catch_repository import CatchRepository
from app.schemas import CatchCreate, CatchRecord, FishSpecies, ForecastDay, ForecastResponse, utcnow


@dataclass(frozen=True)
class WeatherSnapshot:
    day: date
    air_temp_c: float
    pressure_hpa: float
    water_temp_c: float
    wind_speed_m_s: float
    wind_direction_deg: float
    moon_phase: float


class ForecastService:
    def __init__(
        self,
        catch_repository: CatchRepository,
        historical_snapshot_loader: Callable[[date], list[WeatherSnapshot]] | None = None,
        region: str = "krasnoyarsk",
    ) -> None:
        self._catch_repository = catch_repository
        self._historical_snapshot_loader = historical_snapshot_loader
        self._region = region.lower().strip()

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
    ) -> ForecastResponse:
        species_list = [species] if species else ["pike", "perch"]
        species_bias_map = species_bias_map or {}
        days: list[ForecastDay] = []
        for fish_species in species_list:
            for snapshot in snapshots:
                score, confidence = self._score_species(
                    fish_species,
                    snapshot,
                    bias=species_bias_map.get(fish_species, 0.0),
                )
                days.append(
                    ForecastDay(
                        date=snapshot.day,
                        species=fish_species,
                        score=score,
                        confidence=confidence,
                        air_temp_c=snapshot.air_temp_c,
                        pressure_hpa=snapshot.pressure_hpa,
                        water_temp_c=snapshot.water_temp_c,
                        wind_speed_m_s=snapshot.wind_speed_m_s,
                        wind_direction_deg=snapshot.wind_direction_deg,
                        moon_phase=snapshot.moon_phase,
                        stale=stale,
                    )
                )
        return ForecastResponse(generated_at=utcnow(), last_updated_at=last_updated_at, days=days)

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
        for offset in range(7):
            current_day = today + timedelta(days=offset)
            seasonal = math.sin((current_day.timetuple().tm_yday / 365) * 2 * math.pi)
            moon_phase = ((current_day.toordinal() % 29.53) / 29.53)
            air_temp = round(9 + seasonal * 8 + offset * 0.2, 1)
            pressure = round(1008 + math.cos(offset / 2) * 6, 1)
            water_temp = round(6 + seasonal * 4 + offset * 0.15, 1)
            wind_speed = round(2.0 + abs(math.sin(offset + seasonal)) * 5.0, 1)
            wind_direction = round((210 + offset * 18) % 360, 1)
            snapshots.append(
                WeatherSnapshot(
                    day=current_day,
                    air_temp_c=air_temp,
                    pressure_hpa=pressure,
                    water_temp_c=water_temp,
                    wind_speed_m_s=wind_speed,
                    wind_direction_deg=wind_direction,
                    moon_phase=round(moon_phase, 2),
                )
            )
        return snapshots

    def default_snapshots(self) -> list[WeatherSnapshot]:
        return self._daily_snapshots()

    def score_species(self, species: FishSpecies, snapshot: WeatherSnapshot, bias: float = 0.0) -> tuple[float, float]:
        return self._score_species(species, snapshot, bias=bias)

    def _score_species(self, species: FishSpecies, snapshot: WeatherSnapshot, bias: float = 0.0) -> tuple[float, float]:
        profile = self._region_profile(species)
        if species == "pike":
            score = 2.8
            score += (12 - abs(snapshot.water_temp_c - 12)) * 0.11
            score += (1015 - abs(snapshot.pressure_hpa - 1015)) * 0.003
            score += (0.5 - abs(snapshot.moon_phase - 0.5)) * 0.6
            score += self._wind_speed_factor(
                snapshot.wind_speed_m_s,
                optimal=profile["wind_optimal"],
                spread=profile["wind_spread"],
                weight=profile["wind_weight"],
            )
            score += self._wind_direction_factor(
                snapshot.wind_direction_deg,
                preferred_deg=profile["preferred_wind_deg"],
                weight=profile["wind_dir_weight"],
            )
            score += self._season_factor(snapshot.day, species="pike")
            confidence = 0.7
        else:
            score = 2.5
            score += (15 - abs(snapshot.water_temp_c - 15)) * 0.12
            score += (1012 - abs(snapshot.pressure_hpa - 1012)) * 0.0025
            score += (0.5 - abs(snapshot.moon_phase - 0.35)) * 0.55
            score += self._wind_speed_factor(
                snapshot.wind_speed_m_s,
                optimal=profile["wind_optimal"],
                spread=profile["wind_spread"],
                weight=profile["wind_weight"],
            )
            score += self._wind_direction_factor(
                snapshot.wind_direction_deg,
                preferred_deg=profile["preferred_wind_deg"],
                weight=profile["wind_dir_weight"],
            )
            score += self._season_factor(snapshot.day, species="perch")
            confidence = 0.68

        score += bias
        normalized_score = max(0.0, min(5.0, round(score, 2)))
        normalized_confidence = max(0.0, min(1.0, round(confidence, 2)))
        return normalized_score, normalized_confidence

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
        month = day.month
        if species == "pike":
            if month in {5, 6, 9, 10}:
                return 0.26
            if month in {4}:
                return 0.18
            if month in {7, 8}:
                return -0.1
            if month in {11}:
                return -0.02
            return -0.08
        if month in {5, 6, 7, 8, 9}:
            return 0.22
        if month in {10, 11}:
            return 0.05
        return -0.1

    def _season_factor_northwest(self, day: date, *, species: FishSpecies) -> float:
        month = day.month
        if species == "pike":
            if month in {4, 5, 6, 9}:
                return 0.24
            if month in {7, 8}:
                return -0.06
            return -0.02
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
        return {
            "preferred_wind_deg": 170.0,
            "wind_optimal": 3.2,
            "wind_spread": 3.5,
            "wind_weight": 0.32,
            "wind_dir_weight": 0.28,
        }
