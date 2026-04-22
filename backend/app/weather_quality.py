from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.settings import Settings
from app.weather_repository import WeatherRepository


@dataclass
class WeatherQualityResult:
    status: str
    checks: dict


class WeatherQualityService:
    def __init__(self, settings: Settings, weather_repository: WeatherRepository) -> None:
        self._settings = settings
        self._weather_repository = weather_repository

    def run_checks(self) -> WeatherQualityResult:
        now = datetime.now(UTC)
        today = now.date()
        rows = self._weather_repository.get_window_models(today, 7)
        last_updated_at = self._weather_repository.get_last_updated_at()

        completeness_ok = len(rows) >= 7
        expected_days = {(today + timedelta(days=i)) for i in range(7)}
        actual_days = {row.day for row in rows}
        missing_days = sorted(str(day) for day in (expected_days - actual_days))

        freshness_ok = False
        freshness_age_hours = None
        if last_updated_at is not None:
            age = now - last_updated_at
            freshness_age_hours = round(age.total_seconds() / 3600, 2)
            freshness_ok = age <= timedelta(hours=self._settings.forecast_freshness_hours)

        range_issues: list[dict] = []
        for row in rows:
            if not (-60 <= row.air_temp_c <= 60):
                range_issues.append({"day": str(row.day), "field": "air_temp_c", "value": row.air_temp_c})
            if not (850 <= row.pressure_hpa <= 1100):
                range_issues.append({"day": str(row.day), "field": "pressure_hpa", "value": row.pressure_hpa})
            if not (-2 <= row.water_temp_c <= 35):
                range_issues.append({"day": str(row.day), "field": "water_temp_c", "value": row.water_temp_c})
            if not (0 <= row.moon_phase <= 1):
                range_issues.append({"day": str(row.day), "field": "moon_phase", "value": row.moon_phase})

        checks = {
            "freshness": {
                "ok": freshness_ok,
                "last_updated_at": last_updated_at,
                "age_hours": freshness_age_hours,
                "max_age_hours": self._settings.forecast_freshness_hours,
            },
            "completeness": {
                "ok": completeness_ok and len(missing_days) == 0,
                "rows": len(rows),
                "expected_rows": 7,
                "missing_days": missing_days,
            },
            "range": {
                "ok": len(range_issues) == 0,
                "issues": range_issues,
            },
            "duplicates": {
                "ok": len(actual_days) == len(rows),
                "unique_days": len(actual_days),
                "rows": len(rows),
            },
        }

        overall_ok = all(section["ok"] for section in checks.values())
        return WeatherQualityResult(status="ok" if overall_ok else "degraded", checks=checks)
