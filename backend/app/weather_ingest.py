import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import urlencode
from urllib.request import urlopen

from app.forecast_service import WeatherSnapshot
from app.schemas import utcnow
from app.settings import Settings
from app.water_temp_source import WaterTempSnapshot, WaterTempSource
from app.weather_repository import WeatherRepository

logger = logging.getLogger("fishing_forecast.weather_ingest")

# Bay-center coordinates for per-zone Open-Meteo fetches. Approximate
# representative points on the Krasnoyarsk reservoir. The "default" zone
# falls back to settings.location_lat/lon (currently the Krasnoyarsk
# city / dam area) for backward compatibility.
#
# Coordinates are rough — Open-Meteo grid resolution is ~10 km so any
# point within a bay resolves to similar weather. Operators can fine-tune
# these later if needed.
BAY_CENTERS: dict[str, tuple[float, float]] = {
    # South — shallow warm bays.
    "tubinsky": (54.05, 91.40),  # р. Туба, southernmost
    "karasug": (54.30, 91.30),   # р. Карасуг
    "ubey": (54.45, 91.30),      # р. Убей
    "yezagash": (54.50, 91.40),  # р. Езагаш, swampy
    "syda": (54.55, 91.50),      # р. Сыда
    "koma": (54.65, 91.25),      # р. Кома, narrow
    "izhul": (54.70, 91.55),     # р. Ижуль
    "ogur": (54.80, 91.40),      # р. Огур
    "anash": (54.85, 91.45),     # р. Анаша
    # Central.
    "derbino": (55.10, 91.45),   # р. Дербина
    "sisim": (55.30, 92.00),     # р. Сисим
    # North — deeper, cooler.
    "biryusa": (55.55, 92.50),   # р. Бирюса, near dam
    # Open water.
    "main_channel": (55.00, 91.70),  # central main channel
}


@dataclass
class WeatherIngestResult:
    rows: int
    fetched_at: datetime
    source: str
    zones: dict[str, int]


class WeatherIngestService:
    def __init__(
        self,
        settings: Settings,
        weather_repository: WeatherRepository,
        water_temp_source: WaterTempSource | None = None,
    ) -> None:
        self._settings = settings
        self._weather_repository = weather_repository
        self._water_temp_source = water_temp_source or WaterTempSource()

    def ingest_daily_forecast(self) -> WeatherIngestResult:
        # Water-temperature source is reservoir-wide (single
        # temperaturavody.com page), fetch it once and reuse for all zones.
        water_temp_snapshot = self._water_temp_source.fetch()
        fetched_at = utcnow()

        targets: list[tuple[str, float, float]] = [
            ("default", self._settings.location_lat, self._settings.location_lon),
        ]
        for zone, (lat, lon) in BAY_CENTERS.items():
            targets.append((zone, lat, lon))

        zones_rows: dict[str, int] = {}
        first_source = None
        total_rows = 0
        for zone, lat, lon in targets:
            try:
                weather_payload = self._fetch_open_meteo_weather(lat=lat, lon=lon)
                marine_payload = self._fetch_open_meteo_marine(lat=lat, lon=lon)
            except Exception:
                logger.exception("zone_weather_fetch_failed", extra={"zone": zone})
                zones_rows[zone] = 0
                continue
            snapshots, source = self._transform(weather_payload, marine_payload, water_temp_snapshot)
            self._weather_repository.upsert_snapshots(
                snapshots, source=source, fetched_at=fetched_at, zone=zone
            )
            zones_rows[zone] = len(snapshots)
            total_rows += len(snapshots)
            if first_source is None:
                first_source = source

        return WeatherIngestResult(
            rows=total_rows,
            fetched_at=fetched_at,
            source=first_source or "unknown",
            zones=zones_rows,
        )

    def _fetch_open_meteo_weather(self, lat: float | None = None, lon: float | None = None) -> dict:
        params = urlencode(
            {
                "latitude": lat if lat is not None else self._settings.location_lat,
                "longitude": lon if lon is not None else self._settings.location_lon,
                "timezone": "UTC",
                "past_days": 2,
                "forecast_days": 7,
                "wind_speed_unit": "ms",
                "daily": ",".join([
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "temperature_2m_mean",
                    "pressure_msl_mean",
                    "wind_speed_10m_max",
                    "wind_direction_10m_dominant",
                    "cloud_cover_mean",
                    "precipitation_sum",
                    "relative_humidity_2m_mean",
                    "sunrise",
                    "sunset",
                    "daylight_duration",
                ]),
                "hourly": "pressure_msl",
            }
        )
        url = f"https://api.open-meteo.com/v1/forecast?{params}"
        with urlopen(url, timeout=15) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)

    def _fetch_open_meteo_marine(self, lat: float | None = None, lon: float | None = None) -> dict | None:
        params = urlencode(
            {
                "latitude": lat if lat is not None else self._settings.location_lat,
                "longitude": lon if lon is not None else self._settings.location_lon,
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

    def _transform(
        self,
        weather_payload: dict,
        marine_payload: dict | None,
        water_temp_snapshot: WaterTempSnapshot | None = None,
    ) -> tuple[list[WeatherSnapshot], str]:
        daily = weather_payload.get("daily", {})
        days = daily.get("time", [])
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        tmean = daily.get("temperature_2m_mean", [])
        pressure = daily.get("pressure_msl_mean", [])
        wind_speed = daily.get("wind_speed_10m_max", [])
        wind_direction = daily.get("wind_direction_10m_dominant", [])
        cloud_cover = daily.get("cloud_cover_mean", [])
        precipitation = daily.get("precipitation_sum", [])
        humidity = daily.get("relative_humidity_2m_mean", [])
        sunrise_series = daily.get("sunrise", [])
        sunset_series = daily.get("sunset", [])
        daylight_duration = daily.get("daylight_duration", [])

        hourly_pressure_by_day = self._build_hourly_pressure_map(weather_payload)

        marine_map = self._build_marine_map(marine_payload)
        used_marine = False
        used_water_observed = False
        used_water_forecast = False

        snapshots: list[WeatherSnapshot] = []
        prev_daily_pressure: float | None = None
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
            cloud_pct = (
                float(cloud_cover[idx])
                if idx < len(cloud_cover) and cloud_cover[idx] is not None
                else 50.0
            )
            precip_mm = (
                float(precipitation[idx])
                if idx < len(precipitation) and precipitation[idx] is not None
                else 0.0
            )
            humidity_pct = (
                float(humidity[idx])
                if idx < len(humidity) and humidity[idx] is not None
                else 70.0
            )

            sunrise_dt = self._parse_iso_dt(sunrise_series, idx)
            sunset_dt = self._parse_iso_dt(sunset_series, idx)
            if idx < len(daylight_duration) and daylight_duration[idx] is not None:
                daylight_hours = round(float(daylight_duration[idx]) / 3600.0, 2)
            elif sunrise_dt and sunset_dt:
                daylight_hours = round((sunset_dt - sunrise_dt).total_seconds() / 3600.0, 2)
            else:
                daylight_hours = 12.0

            day_pressures = hourly_pressure_by_day.get(current_day, [])
            trend_24h = round(pressure_hpa - prev_daily_pressure, 2) if prev_daily_pressure is not None else 0.0
            trend_6h = self._hourly_pressure_trend_6h(day_pressures)
            prev_daily_pressure = pressure_hpa

            # Priority for water temperature:
            # 1) observed value from temperaturavody.com (most accurate for reservoir)
            # 2) forecast value from temperaturavody.com (for near-future days)
            # 3) marine API (sea surface proxy; not great for inland reservoir)
            # 4) air temperature heuristic fallback
            water_temp: float | None = None
            if water_temp_snapshot is not None:
                observed = water_temp_snapshot.observed.get(current_day)
                if observed is not None:
                    water_temp = observed
                    used_water_observed = True
                else:
                    forecast = water_temp_snapshot.forecast.get(current_day)
                    if forecast is not None:
                        water_temp = forecast
                        used_water_forecast = True
            if water_temp is None:
                marine_temp = marine_map.get(current_day)
                if marine_temp is not None:
                    water_temp = marine_temp
                    used_marine = True
            if water_temp is None:
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
                    cloud_cover_pct=max(0.0, min(100.0, round(cloud_pct, 1))),
                    precipitation_mm=max(0.0, round(precip_mm, 2)),
                    humidity_pct=max(0.0, min(100.0, round(humidity_pct, 1))),
                    pressure_trend_6h_hpa=trend_6h,
                    pressure_trend_24h_hpa=trend_24h,
                    daylight_hours=daylight_hours,
                    sunrise=sunrise_dt,
                    sunset=sunset_dt,
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
        water_sources: list[str] = []
        if used_water_observed:
            water_sources.append("temperaturavody-obs")
        if used_water_forecast:
            water_sources.append("temperaturavody-fc")
        if used_marine:
            water_sources.append("marine")
        if not water_sources:
            water_sources.append("air-proxy")
        source = "open-meteo(fact+forecast)+" + "+".join(water_sources)
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

    def _build_hourly_pressure_map(self, payload: dict) -> dict[date, list[tuple[datetime, float]]]:
        hourly = payload.get("hourly", {})
        times = hourly.get("time", [])
        pressures = hourly.get("pressure_msl", [])
        result: dict[date, list[tuple[datetime, float]]] = {}
        for idx, time_value in enumerate(times):
            if idx >= len(pressures) or pressures[idx] is None:
                continue
            try:
                dt = datetime.fromisoformat(time_value).replace(tzinfo=UTC)
            except ValueError:
                continue
            result.setdefault(dt.date(), []).append((dt, float(pressures[idx])))
        return result

    def _hourly_pressure_trend_6h(self, day_pressures: list[tuple[datetime, float]]) -> float:
        if len(day_pressures) < 2:
            return 0.0
        sorted_pts = sorted(day_pressures, key=lambda x: x[0])
        # Find pair ~6h apart with largest absolute change.
        best_trend = 0.0
        best_abs = 0.0
        for i in range(len(sorted_pts)):
            for j in range(i + 1, len(sorted_pts)):
                dt_hours = (sorted_pts[j][0] - sorted_pts[i][0]).total_seconds() / 3600.0
                if 5.5 <= dt_hours <= 6.5:
                    delta = sorted_pts[j][1] - sorted_pts[i][1]
                    if abs(delta) > best_abs:
                        best_abs = abs(delta)
                        best_trend = delta
        return round(best_trend, 2)

    def _parse_iso_dt(self, series: list, idx: int) -> datetime | None:
        if idx >= len(series) or series[idx] is None:
            return None
        try:
            return datetime.fromisoformat(series[idx]).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return None
