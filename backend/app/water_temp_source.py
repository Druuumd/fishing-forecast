"""Fetch real water-temperature observations & short forecast for the
Krasnoyarsk reservoir from temperaturavody.com.

The source publishes a 14-day table (7 past days with observed temperatures,
today, and ~7 forecast days) plus a 30-day observed history inside an inline
JS array. We extract both and expose a simple map date -> celsius.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from urllib.request import Request, urlopen

logger = logging.getLogger("fishing_forecast.water_temp")

DEFAULT_URL = "https://temperaturavody.com/v/russia/krasnoyarskoye-vodokhranilishche-in-yenisei-river"
DEFAULT_TIMEOUT_SEC = 15
USER_AGENT = "Mozilla/5.0 (fishing-forecast water-temp ingest)"

# Russian 3-letter month codes used on the site.
RU_MONTHS: dict[str, int] = {
    "ЯНВ": 1, "ФЕВ": 2, "МАР": 3, "АПР": 4, "МАЙ": 5, "ИЮН": 6,
    "ИЮЛ": 7, "АВГ": 8, "СЕН": 9, "ОКТ": 10, "НОЯ": 11, "ДЕК": 12,
}

# Row format: <tr ...><td>МЕС ДД</td><td>X.X°C</td><td>...°C</td><td>...°C</td></tr>
# columns: date, observed (may be empty), monthly average, forecast (may be empty)
_ROW_RE = re.compile(
    r"<tr[^>]*>"
    r"<td>([А-ЯЁ]{3})\s+(\d{1,2})</td>"
    r"<td>([^<]*)</td>"
    r"<td>([^<]*)</td>"
    r"<td>([^<]*)</td>"
    r"</tr>",
    re.IGNORECASE,
)

# Inline 30-day JS array: const temps = [x, y, z, ...];
_JS_TEMPS_RE = re.compile(r"const\s+temps\s*=\s*\[([^\]]+)\]\s*;")

_TEMP_CELL_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*°?C", re.IGNORECASE)


@dataclass(frozen=True)
class WaterTempReading:
    day: date
    temp_c: float
    kind: str  # "observed" | "forecast"


@dataclass
class WaterTempSnapshot:
    fetched_at: datetime
    source_url: str
    observed: dict[date, float] = field(default_factory=dict)
    forecast: dict[date, float] = field(default_factory=dict)

    def all_readings(self) -> list[WaterTempReading]:
        items: list[WaterTempReading] = []
        items.extend(WaterTempReading(day=d, temp_c=v, kind="observed") for d, v in self.observed.items())
        items.extend(WaterTempReading(day=d, temp_c=v, kind="forecast") for d, v in self.forecast.items())
        return items

    def get(self, day: date) -> float | None:
        if day in self.observed:
            return self.observed[day]
        return self.forecast.get(day)


class WaterTempSource:
    def __init__(
        self,
        url: str = DEFAULT_URL,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
        reference_year: int | None = None,
    ) -> None:
        self._url = url
        self._timeout = timeout_sec
        # reference_year is for tests; when None, use "now".
        self._reference_year = reference_year

    def fetch(self) -> WaterTempSnapshot | None:
        try:
            html = self._download()
        except Exception:
            logger.exception("water_temp_fetch_failed")
            return None
        return self.parse(html)

    def _download(self) -> str:
        req = Request(self._url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ru,en"})
        with urlopen(req, timeout=self._timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def parse(self, html: str) -> WaterTempSnapshot:
        now = datetime.now(UTC)
        today = now.date()
        snapshot = WaterTempSnapshot(fetched_at=now, source_url=self._url)

        ref_year = self._reference_year or today.year

        for match in _ROW_RE.finditer(html):
            month_code = match.group(1).upper()
            day_num = int(match.group(2))
            observed_cell = match.group(3)
            forecast_cell = match.group(5)
            month = RU_MONTHS.get(month_code)
            if not month:
                continue
            row_date = self._resolve_date(month, day_num, today, ref_year)
            observed = self._parse_temp(observed_cell)
            if observed is not None:
                snapshot.observed[row_date] = observed
            forecast_val = self._parse_temp(forecast_cell)
            if forecast_val is not None and row_date not in snapshot.observed:
                snapshot.forecast[row_date] = forecast_val

        # 30-day history (inline JS): extend observed series backwards from today.
        js_match = _JS_TEMPS_RE.search(html)
        if js_match:
            raw = js_match.group(1)
            values: list[float] = []
            for chunk in raw.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                try:
                    values.append(float(chunk))
                except ValueError:
                    continue
            # Values end at today (last index == today). Walk backwards.
            for i, value in enumerate(reversed(values)):
                day = today - timedelta(days=i)
                snapshot.observed.setdefault(day, value)

        return snapshot

    def _parse_temp(self, cell: str) -> float | None:
        if not cell:
            return None
        m = _TEMP_CELL_RE.search(cell)
        if not m:
            return None
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None

    def _resolve_date(self, month: int, day: int, today: date, ref_year: int) -> date:
        # The table wraps across year boundary (e.g. ДЕК ... ЯНВ). Pick the year
        # that minimises the distance to today so that ~±14 days match the intent.
        candidates = [
            date(ref_year, month, day),
            date(ref_year - 1, month, day),
            date(ref_year + 1, month, day),
        ]
        return min(candidates, key=lambda d: abs((d - today).days))
