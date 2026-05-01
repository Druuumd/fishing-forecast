"""Adverse-conditions warnings for the angler.

Computes a list of active warnings from the existing forecast + water
level state + calendar, so the user sees a clear "don't go" or "watch
out" banner before they read the score cards.

Pure-function design: takes already-computed forecast days and water
level state, returns a deterministic list. No DB calls. Easy to test.

Severity levels (drives UI colour):
  * danger — physically unsafe or fishing prohibited
  * warn   — likely to spoil the trip but not dangerous
  * info   — heads-up / context

Each warning carries a stable ``code`` (machine-friendly) plus
human-readable title/body in Russian.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


SEVERITY_DANGER = "danger"
SEVERITY_WARN = "warn"
SEVERITY_INFO = "info"


@dataclass(frozen=True)
class Warning:
    code: str
    severity: str  # SEVERITY_*
    title: str
    body: str
    valid_from: date | None = None
    valid_to: date | None = None


# -- Spawning ban --------------------------------------------------------

# Krasnoyarsk reservoir is in Восточно-Сибирский рыбохозяйственный бассейн
# (приказ Минсельхоза №226 от 13.05.2020 + поправки 2023). Default period
# for reservoirs in Krasnoyarsk Krai: **25 апреля – 25 июня**, full ban
# except one float/bottom rod from shore outside spawning sites.
# Override via SPAWNING_BAN_START_MD / SPAWNING_BAN_END_MD env vars when
# regulations are amended.
DEFAULT_SPAWNING_BAN_START_MD = "04-25"
DEFAULT_SPAWNING_BAN_END_MD = "06-25"


def _parse_md(s: str) -> tuple[int, int]:
    """Parse 'MM-DD' into (month, day). Tolerant — falls back to defaults."""
    try:
        m, d = s.split("-")
        return (int(m), int(d))
    except (ValueError, AttributeError):
        return (4, 25)


def _within_calendar_window(today: date, start_md: tuple[int, int], end_md: tuple[int, int]) -> bool:
    start = date(today.year, *start_md)
    end = date(today.year, *end_md)
    return start <= today <= end


# -- Public API ----------------------------------------------------------


def compute_warnings(
    *,
    today: date,
    forecast_days: list,
    water_level_state=None,
    lookahead_days: int = 3,
    spawning_ban_start_md: str = DEFAULT_SPAWNING_BAN_START_MD,
    spawning_ban_end_md: str = DEFAULT_SPAWNING_BAN_END_MD,
) -> list[Warning]:
    """Compute the set of active warnings.

    forecast_days: an iterable of objects exposing the same attributes as
    ForecastDay (date, score, factors, wind_speed_m_s, precipitation_mm).
    Pass ForecastDay pydantic models OR the dicts they serialise to —
    both work because we use ``getattr``/``__getitem__`` lookalikes.
    """
    warnings: list[Warning] = []

    if forecast_days:
        warnings.extend(_pressure_shock_warning(forecast_days, lookahead_days))
        warnings.extend(_severe_weather_warning(forecast_days, lookahead_days))
        warnings.extend(_gale_wind_warning(forecast_days, lookahead_days))
        warnings.extend(_heavy_rain_warning(forecast_days, lookahead_days))
        warnings.extend(_ice_unsafe_warning(forecast_days, lookahead_days))

    if water_level_state is not None:
        warnings.extend(_drawdown_warning(water_level_state))

    warnings.extend(_spawning_ban_warning(today, spawning_ban_start_md, spawning_ban_end_md))
    warnings.extend(_species_spawning_warnings(today, forecast_days))

    return warnings


def _species_spawning_warnings(today: date, days) -> list[Warning]:
    """Per-species spawn advisories triggered by current water temperature.

    Looks at today's first available snapshot (already zone-adjusted via
    the forecast pipeline that builds these days). For each of pike /
    perch / bream we emit at most one warning when the species enters
    its active or post-spawn window. We pull the temperature from the
    forecast day rather than guessing — the day already has whatever
    zone offset and per-zone Open-Meteo data was used.
    """
    if not days:
        return []
    from app.species_spawning import species_spawn_state

    out: list[Warning] = []
    today_day = days[0]
    tw = _attr(today_day, "water_temp_c")
    day_date = _attr(today_day, "date")
    if tw is None or day_date is None:
        return []

    severity_for_phase = {"active": SEVERITY_INFO, "post": SEVERITY_INFO}
    for species_code in ("pike", "perch", "bream"):
        state = species_spawn_state(
            species=species_code, day=day_date,
            water_temp_c=float(tw),
        )
        if state.phase not in ("active", "post"):
            continue
        out.append(Warning(
            code=f"{species_code}_spawning",
            severity=severity_for_phase[state.phase],
            title=state.label,
            body=state.body,
            valid_from=day_date,
        ))
    return out


# -- Individual rule helpers ---------------------------------------------


def _gate_active(day, gate_name: str) -> bool:
    factors = _attr(day, "factors") or []
    for f in factors:
        if _attr(f, "name") == gate_name:
            return True
    return False


def _attr(obj, name):
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _pressure_shock_warning(days, lookahead):
    hits = [d for d in days[:lookahead] if _gate_active(d, "pressure_shock_gate")]
    if not hits:
        return []
    first = hits[0]
    return [Warning(
        code="pressure_shock",
        severity=SEVERITY_WARN,
        title="Резкий скачок давления",
        body=(
            f"Барический шок в ближайшие дни (от {_attr(first, 'date')}). "
            "Рыба обычно «закрывает рот» на 1–2 суток. Лучше отложить выезд "
            "или ловить на проверенных перспективных точках."
        ),
        valid_from=_attr(first, "date"),
        valid_to=_attr(hits[-1], "date"),
    )]


def _severe_weather_warning(days, lookahead):
    hits = [d for d in days[:lookahead] if _gate_active(d, "severe_weather_gate")]
    if not hits:
        return []
    first = hits[0]
    return [Warning(
        code="severe_weather",
        severity=SEVERITY_DANGER,
        title="Шторм / сильное ненастье",
        body=(
            f"Сильный ветер вместе с ливнем ожидается с {_attr(first, 'date')}. "
            "На воде небезопасно — особенно в открытой части акватории. "
            "Не выходите на лодке."
        ),
        valid_from=_attr(first, "date"),
        valid_to=_attr(hits[-1], "date"),
    )]


def _gale_wind_warning(days, lookahead):
    threshold = 12.0
    hits = []
    for d in days[:lookahead]:
        wind = _attr(d, "wind_speed_m_s")
        if wind is not None and wind >= threshold:
            hits.append((d, wind))
    if not hits:
        return []
    first_day, first_wind = hits[0]
    peak = max(w for _, w in hits)
    return [Warning(
        code="gale_wind",
        severity=SEVERITY_WARN,
        title="Сильный ветер",
        body=(
            f"С {_attr(first_day, 'date')} ожидается ветер до {peak:.0f} м/с. "
            "Открытая часть водохранилища станет неудобной для лодки; "
            "рассмотрите ловлю в защищённом заливе."
        ),
        valid_from=_attr(first_day, "date"),
        valid_to=_attr(hits[-1][0], "date"),
    )]


def _heavy_rain_warning(days, lookahead):
    threshold = 8.0
    hits = []
    for d in days[:lookahead]:
        precip = _attr(d, "precipitation_mm")
        if precip is not None and precip >= threshold:
            hits.append((d, precip))
    if not hits:
        return []
    first_day, _ = hits[0]
    peak = max(p for _, p in hits)
    return [Warning(
        code="heavy_rain",
        severity=SEVERITY_WARN,
        title="Ливень",
        body=(
            f"Сильный дождь до {peak:.0f} мм в сутки с {_attr(first_day, 'date')}. "
            "Размывает приманку, мутит мелководья, продвинутая ловля затруднена."
        ),
        valid_from=_attr(first_day, "date"),
        valid_to=_attr(hits[-1][0], "date"),
    )]


def _ice_unsafe_warning(days, lookahead):
    """Active 'transition' ice regime — ice is forming or thawing.
    Going on ice in this window is dangerous (thin / rotten ice).
    """
    for d in days[:lookahead]:
        for f in _attr(d, "factors") or []:
            if _attr(f, "name") == "ice_regime":
                detail = _attr(f, "detail") or ""
                if "transition" in detail:
                    return [Warning(
                        code="ice_unsafe",
                        severity=SEVERITY_DANGER,
                        title="Опасный лёд",
                        body=(
                            "Сейчас ледоход или становление льда. На лёд "
                            "выходить нельзя — толщина непредсказуема, "
                            "особенно в местах течения и впадения рек."
                        ),
                        valid_from=_attr(d, "date"),
                    )]
                break
    return []


def _drawdown_warning(state):
    trend = _attr(state, "trend_7d_m") or 0.0
    if trend <= -1.0:
        return [Warning(
            code="drawdown_alarm",
            severity=SEVERITY_WARN,
            title="Резкий сброс воды",
            body=(
                f"Уровень водохранилища упал на {abs(trend):.2f} м за 7 дней — "
                "оперативная сработка ГЭС. Рыба испытывает стресс, "
                "клёв нестабильный, схемы стоянок изменились."
            ),
        )]
    return []


def _spawning_ban_warning(today: date, start_md_str: str, end_md_str: str) -> list[Warning]:
    start_md = _parse_md(start_md_str)
    end_md = _parse_md(end_md_str)
    if not _within_calendar_window(today, start_md, end_md):
        return []
    start = date(today.year, *start_md)
    end = date(today.year, *end_md)
    return [Warning(
        code="spawning_ban",
        severity=SEVERITY_INFO,
        title="Нерестовый запрет",
        body=(
            f"Действует нерестовый запрет на Красноярском водохранилище "
            f"({start.strftime('%d.%m')} – {end.strftime('%d.%m')}, "
            "приказ Минсельхоза №226 для Восточно-Сибирского рыбохозяйственного "
            "бассейна). Разрешена ловля одной поплавочной или донной удочкой "
            "с берега вне нерестовых участков и мест зимовки. Запрещено "
            "передвижение на маломерных судах в нерестовых местах. "
            "Сверяйтесь с актуальными Правилами рыболовства перед выездом."
        ),
        valid_from=start,
        valid_to=end,
    )]
