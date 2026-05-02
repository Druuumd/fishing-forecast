"""Pluggable water-level data sources for the Krasnoyarsk reservoir.

Background — open-data landscape for reservoir levels in Russia
(probed 2026-04-26 from fazendaserv):

* allrivers.info — has gauges only on the Yenisei *river below* the dam,
  not in the reservoir itself. Not useful for our model.
* rushydro.ru / krasges.rushydro.ru — WAF returns no body to non-browser
  User-Agents (TLS handshake completes, body times out). Browser
  emulation possible but brittle.
* gmvo.skniivh.ru, enbvu.ru — informational portals, no open data API.
* gis.favr.ru/opendata — same WAF behaviour as rushydro.
* Telegram public channels (e.g. ОАО «РусГидро Красноярск») post daily
  level reports as plain text — parseable but channel name varies.

For now the authoritative fallback remains manual admin entry
(POST /v1/admin/water-level) plus seasonal climatology in
``WaterLevelService``. The classes below provide the framework so a
new source can be plugged in via WATER_LEVEL_SCRAPE_SOURCE env once a
specific feed is identified.

Design: a Source returns an optional ``WaterLevelObservation``.
Failures (network, CSRF reject, parse, missing data) are caught and
logged at the Source layer — callers always get None on failure rather
than an exception, so the ingest pipeline never falls over because a
third-party site rotated its API or blocked the IP.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

logger = logging.getLogger("fishing_forecast.water_level_source")

USER_AGENT = "Mozilla/5.0 (fishing-forecast water-level ingest)"


@dataclass(frozen=True)
class WaterLevelObservation:
    day: date
    level_m: float
    source: str  # short label e.g. "allrivers:gauge-123"
    inflow_m3s: float | None = None
    outflow_m3s: float | None = None
    note: str | None = None


class WaterLevelSource:
    """Abstract base. Implementations return None on any failure."""

    def fetch(self) -> WaterLevelObservation | None:
        raise NotImplementedError


class AllRiversWaterLevelSource(WaterLevelSource):
    """allrivers.info reverse-engineered fetcher.

    Strategy:
    1. GET the gauge page once. The HTML embeds an inline JS bearer
       like ``const token = "eyJh..."`` and sets a session cookie.
    2. POST to /get_brief_charts (or /get_post_data depending on the
       site version) using the bearer + cookies + matching Origin and
       Referer headers. CSRF rejects external Origins, so we mimic the
       page's own Origin.
    3. Parse the JSON response, take the most recent point, return it
       as a WaterLevelObservation.

    Token rotation, page restructure, or IP blocking will all make
    this return None — that's the contract. We log the failure mode
    so operators can see why scraping stopped working.
    """

    BEARER_PATTERNS = (
        re.compile(r"['\"](eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)['\"]"),
        re.compile(r"token\s*[:=]\s*['\"]([^'\"]+)['\"]"),
        re.compile(r"bearer\s*[:=]\s*['\"]([^'\"]+)['\"]", re.IGNORECASE),
    )

    CHART_PATHS = ("/get_brief_charts", "/get_post_data", "/api/post_charts")

    def __init__(
        self,
        page_url: str,
        gauge_id: int,
        timeout_sec: int = 15,
    ) -> None:
        self._page_url = page_url
        self._gauge_id = gauge_id
        self._timeout = timeout_sec
        self._cookies = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._cookies))

    def fetch(self) -> WaterLevelObservation | None:
        if not self._page_url or self._gauge_id == 0:
            logger.warning(
                "allrivers_source_unconfigured",
                extra={"page_url": self._page_url, "gauge_id": self._gauge_id},
            )
            return None
        try:
            html = self._download_page()
        except (HTTPError, URLError, TimeoutError) as exc:
            logger.warning("allrivers_page_unreachable", extra={"err": str(exc)})
            return None
        bearer = self._extract_bearer(html)
        if bearer is None:
            logger.warning("allrivers_bearer_not_found")
            return None
        for path in self.CHART_PATHS:
            try:
                data = self._fetch_chart(path, bearer)
            except (HTTPError, URLError, TimeoutError) as exc:
                logger.warning(
                    "allrivers_chart_failed",
                    extra={"path": path, "status": getattr(exc, "code", None), "err": str(exc)},
                )
                continue
            obs = self._parse(data)
            if obs is not None:
                return obs
        logger.warning("allrivers_all_chart_paths_failed")
        return None

    def _download_page(self) -> str:
        req = Request(
            self._page_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "ru,en",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with self._opener.open(req, timeout=self._timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")

    def _extract_bearer(self, html: str) -> str | None:
        for pattern in self.BEARER_PATTERNS:
            m = pattern.search(html)
            if m:
                token = m.group(1)
                if len(token) >= 20:  # sanity-check, JWTs are long
                    return token
        return None

    def _fetch_chart(self, path: str, bearer: str) -> dict:
        parsed = urlparse(self._page_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        url = urljoin(origin, path)
        body = json.dumps({"item": self._gauge_id, "id": self._gauge_id}).encode("utf-8")
        req = Request(
            url,
            data=body,
            method="POST",
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {bearer}",
                "Origin": origin,
                "Referer": self._page_url,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        with self._opener.open(req, timeout=self._timeout) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
        return json.loads(payload)

    def _parse(self, data: dict) -> WaterLevelObservation | None:
        # The actual response shape varies between API revisions. Try a
        # few known shapes; return the first one that yields a valid
        # (date, level) pair.
        candidates = [
            data,
            data.get("data") if isinstance(data.get("data"), dict) else None,
            data.get("result") if isinstance(data.get("result"), dict) else None,
        ]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            obs = self._extract_latest_point(candidate)
            if obs is not None:
                return obs
        return None

    def _extract_latest_point(self, payload: dict) -> WaterLevelObservation | None:
        # Look for arrays of {date, level} or {x, y} or parallel x/y arrays.
        for key_xy in ("levels", "points", "series", "chart"):
            series = payload.get(key_xy)
            if isinstance(series, list) and series:
                last = series[-1]
                if isinstance(last, dict):
                    day = self._parse_date(last.get("date") or last.get("x") or last.get("t"))
                    level = self._parse_level(last.get("level") or last.get("y") or last.get("value"))
                    if day and level is not None:
                        return WaterLevelObservation(
                            day=day,
                            level_m=level,
                            source=f"allrivers:gauge-{self._gauge_id}",
                            note=f"auto-scrape via {key_xy}",
                        )
        xs = payload.get("x") or payload.get("dates")
        ys = payload.get("y") or payload.get("levels")
        if isinstance(xs, list) and isinstance(ys, list) and xs and ys:
            day = self._parse_date(xs[-1])
            level = self._parse_level(ys[-1])
            if day and level is not None:
                return WaterLevelObservation(
                    day=day,
                    level_m=level,
                    source=f"allrivers:gauge-{self._gauge_id}",
                    note="auto-scrape via x/y arrays",
                )
        return None

    @staticmethod
    def _parse_date(raw) -> date | None:
        if raw is None:
            return None
        if isinstance(raw, (int, float)):
            try:
                return datetime.fromtimestamp(raw / 1000 if raw > 1_000_000_000_000 else raw, UTC).date()
            except (OSError, ValueError, OverflowError):
                return None
        if isinstance(raw, str):
            for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(raw[:19], fmt).date()
                except ValueError:
                    continue
        return None

    @staticmethod
    def _parse_level(raw) -> float | None:
        if raw is None:
            return None
        try:
            value = float(str(raw).replace(",", "."))
        except (TypeError, ValueError):
            return None
        # Sanity-check: Krasnoyarsk reservoir is bounded UMO 225 to NPU 243.
        # If the source emits a different unit (cm above gauge zero), reject.
        if 200.0 <= value <= 250.0:
            return value
        return None


class StaticWaterLevelSource(WaterLevelSource):
    """Stub source for tests / demos: returns a fixed observation."""

    def __init__(self, observation: WaterLevelObservation | None) -> None:
        self._observation = observation

    def fetch(self) -> WaterLevelObservation | None:
        return self._observation


def create_source_from_settings(settings) -> WaterLevelSource | None:
    if not settings.water_level_scrape_enabled:
        return None
    name = (settings.water_level_scrape_source or "").lower()
    if name == "allrivers":
        return AllRiversWaterLevelSource(
            page_url=settings.water_level_scrape_page_url,
            gauge_id=settings.water_level_scrape_gauge_id,
            timeout_sec=settings.water_level_scrape_timeout_sec,
        )
    logger.warning("water_level_source_unknown", extra={"name": name})
    return None
