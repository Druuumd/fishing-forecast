import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import urlencode
from urllib.request import urlopen

from app.forecast_service import WeatherSnapshot
from app.schemas import utcnow
from app.settings import Settings
from app.weather_repository import WeatherRepository

logger = logging.getLogger("fishing_forecast.weather_ingest")


@dataclass
class WeatherIngestResult:
    rows: int
    fetched_at: datetime
    source: str


class WeatherIngestService:
    def __init__(self, settings: Settings, weather_repository: WeatherRepository) -> None:
        self._settings = settings
        self._weather_repository = weather_repository

    def ingest_daily_forecast(self) -> WeatherIngestResult:
        weather_payload = self._fetch_open_meteo_weather()
        marine_payload = self._fetch_open_meteo_marine()
        snapshots, source = self._transform(weather_payload, marine_payload)
        fetched_at = utcnow()
        self._weather_repository.upsert_snapshots(snapshots, source=source, fetched_at=fetched_at)
        return WeatherIngestResult(rows=len(snapshots), fetched_at=fetched_at, source=source)

    def _fetch_open_meteo_weather(self) -> dict:
        params = urlencode(
            {
                "latitude": self._settings.location_lat,
                "longitude": self._settings.location_lon,
                "timezone": "UTC",
                "past_days": 2,
                "forecast_days": 7,
                "wind_speed_unit": "ms",
                "daily": "temperature_2m_max,temperature_2m_min,temperature_2m_mean,pressure_msl_mean,wind_speed_10m_max,wind_direction_10m_dominant",
            }
        )
        url = f"https://api.open-meteo.com/v1/forecast?{params}"
        with urlopen(url, timeout=15) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)

    def _fetch_open_meteo_marine(self) -> dict | None:
        params = urlencode(
            {
                "latitude": self._settings.location_lat,
                "longitude": self._settings.location_lon,
                "timezone": "UTC",
                "past_days": 2,
                "forecast_days": 7,
                "daily": "sea_surface_temperature_max,sea_surface_temperature_min,sea_surface_temperature_mean",
            }
        )
        url = f"https://marine-api.open-meteo.com/v1/marine?{params}"
        try:
            with urlopen(url, timeout=15) as response:
                body = response.read().decode("utf-8")
            return json.loads(body)
        except Exception:
            logger.exception("marine_fetch_failed")
            return None

    def _transform(self, weather_payload: dict, marine_payload: dict | None) -> tuple[list[WeatherSnapshot], str]:
        daily = weather_payload.get("daily", {})
        days = daily.get("time", [])
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        tmean = daily.get("temperature_2m_mean", [])
        pressure = daily.get("pressure_msl_mean", [])
        wind_speed = daily.get("wind_speed_10m_max", [])
        wind_direction = daily.get("wind_direction_10m_dominant", [])
        marine_map = self._build_marine_map(marine_payload)
        used_marine = False

        snapshots: list[WeatherSnapshot] = []
        for idx, day_value in enumerate(days):
            current_day = date.fromisoformat(day_value)
            raw_tmean = tmean[idx] if idx < len(tmean) else None
            raw_tmax = tmax[idx] if idx < len(tmax) else None
            raw_tmin = tmin[idx] if idx < len(tmin) else None
            if raw_tmean is not None:
                air_temp = float(raw_tmean)
            elif raw_tmax is not None and raw_tmin is not None:
                air_temp = (float(raw_tmax) + float(raw_tmin)) / 2
            elif raw_tmax is not None:
                air_temp = float(raw_tmax)
            else:
                air_temp = 0.0
            pressure_hpa = float(pressure[idx]) if idx < len(pressure) and pressure[idx] is not None else 1013.0
            wind_speed_m_s = (
                float(wind_speed[idx])
                if idx < len(wind_speed) and wind_speed[idx] is not None
                else 3.0
            )
            wind_direction_deg = (
                float(wind_direction[idx])
                if idx < len(wind_direction) and wind_direction[idx] is not None
                else 180.0
            )

            marine_temp = marine_map.get(current_day)
            if marine_temp is not None:
                water_temp = marine_temp
                used_marine = True
            else:
                # Fallback proxy when marine endpoint is unavailable for location/day.
                water_temp = round((air_temp * 0.45) + 4.0, 1)
            moon_phase = round(((current_day.toordinal() % 29.53) / 29.53), 2)

            snapshots.append(
                WeatherSnapshot(
                    day=current_day,
                    air_temp_c=round(air_temp, 1),
                    pressure_hpa=round(pressure_hpa, 1),
                    water_temp_c=water_temp,
                    wind_speed_m_s=round(wind_speed_m_s, 1),
                    wind_direction_deg=round(wind_direction_deg % 360, 1),
                    moon_phase=max(0.0, min(1.0, moon_phase)),
                )
            )

        if not snapshots:
            today = datetime.now(UTC).date()
            snapshots.append(
                WeatherSnapshot(
                    day=today,
                    air_temp_c=8.0,
                    pressure_hpa=1013.0,
                    water_temp_c=7.0,
                    wind_speed_m_s=3.0,
                    wind_direction_deg=180.0,
                    moon_phase=0.5,
                )
            )
        source = "open-meteo(fact+forecast)+marine" if used_marine else "open-meteo(fact+forecast)+proxy"
        return snapshots, source

    def _build_marine_map(self, marine_payload: dict | None) -> dict[date, float]:
        if not marine_payload:
            return {}
        daily = marine_payload.get("daily", {})
        days = daily.get("time", [])
        sea_max = daily.get("sea_surface_temperature_max", [])
        sea_min = daily.get("sea_surface_temperature_min", [])
        sea_mean = daily.get("sea_surface_temperature_mean", [])

        mapped: dict[date, float] = {}
        for idx, day_value in enumerate(days):
            current_day = date.fromisoformat(day_value)
            mean_value = sea_mean[idx] if idx < len(sea_mean) else None
            max_value = sea_max[idx] if idx < len(sea_max) else None
            min_value = sea_min[idx] if idx < len(sea_min) else None

            water_temp = None
            if mean_value is not None:
                water_temp = float(mean_value)
            elif max_value is not None and min_value is not None:
                water_temp = (float(max_value) + float(min_value)) / 2

            if water_temp is not None:
                mapped[current_day] = round(water_temp, 1)
        return mapped
