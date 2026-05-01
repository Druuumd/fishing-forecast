import logging
from datetime import UTC, datetime, timedelta
from time import perf_counter

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import AuthUser, LoginRequest, LoginResponse, authenticate_demo_user, get_current_user
from app.cache import ForecastCache, create_redis_client
from app.catch_guard import CatchGuard
from app.catch_repository import CatchRepository
from app.consent_repository import ConsentRepository
from app.db import create_db_engine
from app.errors import ApiError, api_error_payload
from app.forecast_service import ForecastService, WaterLevelContext
from app.logging_config import configure_logging, new_trace_id, trace_id_ctx
from app.ml_repository import MlRepository
from app.ml_service import MlService, PublishResult, RetrainResult
from app.schemas import CatchCreate, CatchRecord, ConsentRecord, ConsentUpdate, FishSpecies, ForecastResponse, utcnow
from app.schemas import DeleteMeDataResponse, LegalInfoResponse, MeDataExportResponse
from app.schemas import (
    PushConditionTypeInfo,
    PushConditionTypesResponse,
    PushSubscriptionCreate,
    PushSubscriptionRecord,
    PushVapidPublicKeyResponse,
    WarningItem,
    WarningsResponse,
    WaterTempReadingCreate,
    WaterTempReadingRecord,
    WaterTempReadingsResponse,
    ZoneCenter,
    ZoneCentersResponse,
    WaterLevelCreate,
    WaterLevelHistoryPoint,
    WaterLevelHistoryResponse,
    WaterLevelResponse,
    WaterLevelStateResponse,
    WeatherHistoryPoint,
    WeatherHistoryResponse,
)
from app.settings import get_settings
from app.water_level_service import (
    WaterLevelIngestService,
    WaterLevelReading,
    WaterLevelRepository,
    WaterLevelService,
)
from app.warnings_service import compute_warnings
from app.water_level_sources import create_source_from_settings
from app.water_temp_readings import (
    WaterTempReadingRepository,
    make_reading as make_water_temp_reading,
    validate_reading as validate_water_temp_reading,
)
from app.push_service import PushService, PushSubscriptionRepository
from app.weather_ingest import WeatherIngestResult, WeatherIngestService
from app.weather_quality import WeatherQualityResult, WeatherQualityService
from app.weather_repository import WeatherRepository

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger("fishing_forecast.api")
db_engine = create_db_engine(settings)
catch_repository = CatchRepository(db_engine)
consent_repository = ConsentRepository(db_engine)
weather_repository = WeatherRepository(db_engine)
ml_repository = MlRepository(db_engine)
water_level_repository = WaterLevelRepository(db_engine)
water_level_service = WaterLevelService(water_level_repository)
water_level_ingest_service = WaterLevelIngestService(
    source=create_source_from_settings(settings),
    repository=water_level_repository,
)
push_repository = PushSubscriptionRepository(db_engine)
water_temp_reading_repository = WaterTempReadingRepository(db_engine)
redis_client = create_redis_client(settings)
forecast_cache = ForecastCache(redis_client, ttl_sec=settings.forecast_cache_ttl_sec)
catch_guard = CatchGuard(
    redis_client=redis_client,
    rate_limit_window_sec=settings.catch_rate_limit_window_sec,
    rate_limit_max_requests=settings.catch_rate_limit_max_requests,
    duplicate_window_sec=settings.catch_duplicate_window_sec,
)


def _load_historical_snapshots(target_day):
    start_day = target_day - timedelta(days=3)
    return weather_repository.get_window(start_day=start_day, days=10)


forecast_service = ForecastService(
    catch_repository=catch_repository,
    historical_snapshot_loader=_load_historical_snapshots,
    region=settings.forecast_region,
    region_elevation_m=settings.forecast_region_elevation_m,
    location_lat=settings.location_lat,
    location_lon=settings.location_lon,
)
weather_ingest_service = WeatherIngestService(settings, weather_repository)
weather_quality_service = WeatherQualityService(settings, weather_repository)
ml_service = MlService(settings, ml_repository, forecast_service)
push_service = PushService(
    repository=push_repository,
    vapid_private_key_pem=settings.vapid_private_key_pem,
    vapid_subject=settings.vapid_subject,
    forecast_service=forecast_service,
    lookahead_days=settings.push_lookahead_days,
)

SUPPORTED_SPECIES: tuple[str, ...] = ("pike", "perch", "bream")
SUPPORTED_ZONES: tuple[str, ...] = (
    "tubinsky", "karasug", "ubey", "yezagash", "syda", "koma",
    "izhul", "ogur", "anash", "derbino", "sisim", "biryusa", "main_channel",
)
FORECAST_CACHE_KEYS: list[str] = []
for _zone in (None, *SUPPORTED_ZONES):
    _zone_part = _zone or "default"
    FORECAST_CACHE_KEYS.append(f"forecast:v2:{_zone_part}:all")
    for _sp in SUPPORTED_SPECIES:
        FORECAST_CACHE_KEYS.append(f"forecast:v2:{_zone_part}:{_sp}")

app = FastAPI(title=settings.app_name)
allowed_origins = [origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    payload = api_error_payload(
        code=exc.code,
        message=exc.message,
        retryable=exc.retryable,
        request_id=trace_id_ctx.get(),
        details=exc.details,
    )
    headers = {}
    if exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS and exc.details:
        retry_after = exc.details.get("retry_after_sec")
        if isinstance(retry_after, int):
            headers["Retry-After"] = str(retry_after)
    return JSONResponse(status_code=exc.status_code, content=payload, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    payload = api_error_payload(
        code="VALIDATION_ERROR",
        message="request validation failed",
        retryable=False,
        request_id=trace_id_ctx.get(),
        details={"issues": exc.errors()},
    )
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=payload)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = f"HTTP_{exc.status_code}"
    retryable = exc.status_code >= 500
    message = exc.detail if isinstance(exc.detail, str) else "http error"
    payload = api_error_payload(
        code=code,
        message=message,
        retryable=retryable,
        request_id=trace_id_ctx.get(),
    )
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", extra={"error_type": type(exc).__name__})
    payload = api_error_payload(
        code="INTERNAL_ERROR",
        message="unexpected server error",
        retryable=True,
        request_id=trace_id_ctx.get(),
    )
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)


def _audit_catch_event(
    *,
    outcome: str,
    source_ip: str,
    user_id: str | None,
    species: str | None,
    score: float | None,
    latitude: float | None,
    longitude: float | None,
    reason: str | None = None,
    catch_id: str | None = None,
) -> None:
    logger.info(
        "catch_submission_audit",
        extra={
            "event_type": "catch_submission",
            "outcome": outcome,
            "source_ip": source_ip,
            "user_id": user_id or "-",
            "species": species,
            "score": score,
            "latitude": latitude,
            "longitude": longitude,
            "reason": reason,
            "catch_id": catch_id,
        },
    )


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = request.headers.get("x-trace-id") or new_trace_id()
    token = trace_id_ctx.set(trace_id)
    started = perf_counter()
    response = None

    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = int((perf_counter() - started) * 1000)
        logger.exception(
            "request_failed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "elapsed_ms": elapsed_ms,
            },
        )
        trace_id_ctx.reset(token)
        raise
    finally:
        if response is not None:
            elapsed_ms = int((perf_counter() - started) * 1000)
            logger.info(
                "request_processed",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "elapsed_ms": elapsed_ms,
                },
            )
            trace_id_ctx.reset(token)

    response.headers["x-trace-id"] = trace_id
    return response


@app.get("/health")
@app.get("/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
@app.get("/v1/ready")
async def ready() -> JSONResponse:
    db_ready = catch_repository.ping()
    redis_ready = forecast_cache.ping()
    status_code = 200 if db_ready else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if db_ready else "degraded",
            "env": settings.app_env,
            "db": "up" if db_ready else "down",
            "redis": "up" if redis_ready else "down",
        },
    )


@app.get("/v1/legal/info", response_model=LegalInfoResponse)
async def legal_info() -> LegalInfoResponse:
    return LegalInfoResponse(
        status="ok",
        contact_email=settings.legal_contact_email,
        support_email=settings.legal_support_email,
        privacy_url=settings.legal_privacy_url,
        terms_url=settings.legal_terms_url,
        data_deletion_url=settings.legal_data_deletion_url,
        cookie_tracking_url=settings.legal_cookie_tracking_url,
        updated_at=utcnow(),
    )


@app.get("/forecast", response_model=ForecastResponse)
@app.get("/v1/forecast", response_model=ForecastResponse)
async def get_forecast(
    species: FishSpecies | None = None,
    zone: str | None = None,
) -> ForecastResponse:
    if zone not in (None, *SUPPORTED_ZONES):
        zone = None
    zone_part = zone or "default"
    cache_key = f"forecast:v2:{zone_part}:{species or 'all'}"
    cached_payload = forecast_cache.get(cache_key)
    if cached_payload:
        return ForecastResponse.model_validate_json(cached_payload)

    today = datetime.now(UTC).date()

    # Try to load zone-specific snapshots first; fall back to "default" zone
    # snapshots if the requested bay hasn't been ingested yet. The flag
    # apply_zone_temp_offset tells the scoring layer whether to add the
    # heuristic Δ°C offset (only needed when we're using default-zone data
    # to approximate a bay).
    apply_zone_temp_offset = True
    snapshots: list = []
    last_updated_at = None
    if zone:
        zone_snapshots = weather_repository.get_window(start_day=today, days=7, zone=zone)
        if len(zone_snapshots) >= 7:
            snapshots = zone_snapshots
            last_updated_at = weather_repository.get_last_updated_at(zone=zone)
            apply_zone_temp_offset = False
    if not snapshots:
        snapshots = weather_repository.get_window(start_day=today, days=7, zone="default")
        last_updated_at = weather_repository.get_last_updated_at(zone="default")
    is_fresh = False
    if last_updated_at is not None:
        freshness_deadline = datetime.now(UTC) - timedelta(hours=settings.forecast_freshness_hours)
        is_fresh = last_updated_at >= freshness_deadline

    active_model = ml_service.active_model()
    species_bias_map = active_model["species_bias"] if active_model else None

    water_state = water_level_service.current_state(today=today)
    water_level_context = WaterLevelContext(
        latest_level_m=water_state.latest_level_m,
        trend_7d_m=water_state.trend_7d_m,
        source=water_state.source,
        is_fresh=water_state.is_fresh,
    )

    if len(snapshots) >= 7 and is_fresh:
        response = forecast_service.build_forecast_from_snapshots(
            snapshots=snapshots[:7],
            species=species,
            stale=False,
            last_updated_at=last_updated_at,
            species_bias_map=species_bias_map,
            water_level=water_level_context,
            zone=zone,
            apply_zone_temp_offset=apply_zone_temp_offset,
        )
    else:
        response = forecast_service.build_forecast_from_snapshots(
            snapshots=forecast_service.default_snapshots(),
            species=species,
            stale=True,
            last_updated_at=last_updated_at,
            species_bias_map=species_bias_map,
            water_level=water_level_context,
            zone=zone,
            apply_zone_temp_offset=True,
        )
    forecast_cache.set(cache_key, response.model_dump_json())
    return response


@app.get("/v1/zones/centers", response_model=ZoneCentersResponse)
async def zone_centers() -> ZoneCentersResponse:
    """Public read: coordinates + label + archetype for the 13 named bays.

    Used by the frontend map to drop bay markers and by any client that
    wants to position a layer over the reservoir without duplicating the
    BAY_CENTERS constant.
    """
    from app.forecast_service import _BAY_REGISTRY
    from app.weather_ingest import BAY_CENTERS

    items: list[ZoneCenter] = []
    for code, (lat, lon) in BAY_CENTERS.items():
        profile = _BAY_REGISTRY.get(code)
        if profile is None:
            continue
        items.append(ZoneCenter(
            code=code,
            label=profile["label"],
            lat=lat,
            lon=lon,
            archetype=profile.get("archetype"),
        ))
    return ZoneCentersResponse(zones=items)


@app.post(
    "/v1/water-temp-readings",
    response_model=WaterTempReadingRecord,
    status_code=status.HTTP_201_CREATED,
)
async def submit_water_temp_reading(
    payload: WaterTempReadingCreate,
    auth_user: AuthUser = Depends(get_current_user),
) -> WaterTempReadingRecord:
    """User-submitted thermal profile measurement.

    Validates aggressively (GPS bbox, temperature ranges, freshness,
    surface > below). Returns 422 with field-level errors when invalid;
    the UI uses them to highlight the offending input.
    """
    vr = validate_water_temp_reading(
        measured_at=payload.measured_at,
        latitude=payload.latitude,
        longitude=payload.longitude,
        surface_temp_c=payload.surface_temp_c,
        thermocline_depth_m=payload.thermocline_depth_m,
        below_thermocline_temp_c=payload.below_thermocline_temp_c,
    )
    if not vr.valid:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="WATER_TEMP_READING_INVALID",
            message="Замер не прошёл валидацию.",
            retryable=False,
            details={"field_errors": vr.errors},
        )
    reading = make_water_temp_reading(
        user_id=auth_user.user_id,
        measured_at=payload.measured_at,
        latitude=payload.latitude,
        longitude=payload.longitude,
        surface_temp_c=payload.surface_temp_c,
        thermocline_depth_m=payload.thermocline_depth_m,
        below_thermocline_temp_c=payload.below_thermocline_temp_c,
        instrument=payload.instrument,
        note=payload.note,
    )
    saved = water_temp_reading_repository.save(reading)
    logger.info(
        "water_temp_reading_saved",
        extra={
            "event_type": "water_temp_reading",
            "user_id": auth_user.user_id,
            "zone": saved.zone,
            "surface_temp_c": saved.surface_temp_c,
            "has_thermocline": saved.thermocline_depth_m is not None,
        },
    )
    return WaterTempReadingRecord(**saved.__dict__)


@app.get("/v1/water-temp-readings", response_model=WaterTempReadingsResponse)
async def list_water_temp_readings(
    zone: str | None = None,
    limit: int = 100,
    days: int = 30,
) -> WaterTempReadingsResponse:
    """Recent user-submitted readings — public read for crowdsourced map."""
    if zone is not None and zone not in SUPPORTED_ZONES:
        zone = None
    limit = max(1, min(500, limit))
    days = max(1, min(60, days))
    readings = water_temp_reading_repository.list_recent(
        zone=zone, limit=limit, max_age_days=days
    )
    return WaterTempReadingsResponse(
        points=[WaterTempReadingRecord(**r.__dict__) for r in readings]
    )


@app.get("/v1/warnings", response_model=WarningsResponse)
async def warnings(zone: str | None = None) -> WarningsResponse:
    """Adverse-conditions warnings — public read.

    Loads the same forecast we'd return from /v1/forecast for the given
    zone, applies the warnings ruleset, and returns active warnings.
    Cheap to call; cached at the forecast layer (cache key includes zone).
    """
    if zone not in (None, *SUPPORTED_ZONES):
        zone = None
    today = datetime.now(UTC).date()
    apply_zone_temp_offset = True
    snapshots: list = []
    if zone:
        zone_snapshots = weather_repository.get_window(start_day=today, days=7, zone=zone)
        if len(zone_snapshots) >= 7:
            snapshots = zone_snapshots
            apply_zone_temp_offset = False
    if not snapshots:
        snapshots = weather_repository.get_window(start_day=today, days=7, zone="default")

    water_state = water_level_service.current_state(today=today)
    water_level_context = WaterLevelContext(
        latest_level_m=water_state.latest_level_m,
        trend_7d_m=water_state.trend_7d_m,
        source=water_state.source,
        is_fresh=water_state.is_fresh,
    )

    if len(snapshots) < 7:
        snapshots = forecast_service.default_snapshots()
    response = forecast_service.build_forecast_from_snapshots(
        snapshots=snapshots[:7],
        species=None,
        stale=False,
        last_updated_at=None,
        species_bias_map=None,
        water_level=water_level_context,
        zone=zone,
        apply_zone_temp_offset=apply_zone_temp_offset,
    )
    # Use first species's day-by-day shape (all species share the same
    # weather/factors mix per day; warnings only depend on weather + gates).
    pike_days = [d for d in response.days if d.species == "pike"]

    items = compute_warnings(
        today=today,
        forecast_days=pike_days,
        water_level_state=water_state,
        spawning_ban_start_md=settings.spawning_ban_start_md,
        spawning_ban_end_md=settings.spawning_ban_end_md,
    )
    return WarningsResponse(
        generated_at=utcnow(),
        zone=response.zone,
        zone_label=response.zone_label,
        warnings=[
            WarningItem(
                code=w.code,
                severity=w.severity,
                title=w.title,
                body=w.body,
                valid_from=w.valid_from,
                valid_to=w.valid_to,
            )
            for w in items
        ],
    )


@app.get("/v1/water-level/history", response_model=WaterLevelHistoryResponse)
async def water_level_history(days: int = 30) -> WaterLevelHistoryResponse:
    days = max(1, min(365, days))
    today = datetime.now(UTC).date()
    start = today - timedelta(days=days - 1)
    readings = water_level_repository.get_window(start, today)
    points = [
        WaterLevelHistoryPoint(day=r.day, level_m=r.level_m, source=r.source)
        for r in readings
    ]
    return WaterLevelHistoryResponse(days_requested=days, points=points)


@app.get("/v1/weather/history", response_model=WeatherHistoryResponse)
async def weather_history(days: int = 14) -> WeatherHistoryResponse:
    days = max(1, min(60, days))
    today = datetime.now(UTC).date()
    start = today - timedelta(days=days - 1)
    snapshots = weather_repository.get_window(start_day=start, days=days)
    points: list[WeatherHistoryPoint] = []
    for s in snapshots:
        surface = forecast_service._surface_pressure_hpa(s.air_temp_c, s.pressure_hpa)
        points.append(
            WeatherHistoryPoint(
                day=s.day,
                air_temp_c=s.air_temp_c,
                pressure_hpa=s.pressure_hpa,
                surface_pressure_hpa=round(surface, 1),
                water_temp_c=s.water_temp_c,
                wind_speed_m_s=s.wind_speed_m_s,
                cloud_cover_pct=s.cloud_cover_pct,
                precipitation_mm=s.precipitation_mm,
                pressure_trend_24h_hpa=s.pressure_trend_24h_hpa,
            )
        )
    return WeatherHistoryResponse(days_requested=days, points=points)


@app.get("/v1/push/vapid-public-key", response_model=PushVapidPublicKeyResponse)
async def push_vapid_public_key() -> PushVapidPublicKeyResponse:
    return PushVapidPublicKeyResponse(
        public_key=settings.vapid_public_key_b64,
        enabled=push_service.enabled,
    )


@app.get("/v1/push/condition-types", response_model=PushConditionTypesResponse)
async def push_condition_types() -> PushConditionTypesResponse:
    """Catalog of available conditions + their parameter shapes for the UI."""
    types = [
        PushConditionTypeInfo(
            type="score_min", label="Минимальная оценка",
            params_schema=[{"name": "min", "kind": "number", "min": 0.0, "max": 5.0, "step": 0.1, "default": 3.5, "label": "оценка ≥"}],
        ),
        PushConditionTypeInfo(
            type="wind_max", label="Максимальный ветер",
            params_schema=[{"name": "max_m_s", "kind": "number", "min": 0.0, "max": 20.0, "step": 0.5, "default": 6.0, "label": "ветер ≤ м/с"}],
        ),
        PushConditionTypeInfo(type="no_pressure_shock", label="Без барического шока"),
        PushConditionTypeInfo(type="no_thermal_shock", label="Без термошока"),
        PushConditionTypeInfo(type="no_severe_weather", label="Без шторма"),
        PushConditionTypeInfo(
            type="no_precipitation", label="Без сильных осадков",
            params_schema=[{"name": "max_mm", "kind": "number", "min": 0.0, "max": 30.0, "step": 0.1, "default": 0.5, "label": "осадки ≤ мм"}],
        ),
        PushConditionTypeInfo(
            type="water_temp_min", label="Минимальная температура воды",
            params_schema=[{"name": "min", "kind": "number", "min": -2.0, "max": 30.0, "step": 0.5, "default": 8.0, "label": "Tw ≥ °C"}],
        ),
        PushConditionTypeInfo(
            type="water_temp_max", label="Максимальная температура воды",
            params_schema=[{"name": "max", "kind": "number", "min": 0.0, "max": 30.0, "step": 0.5, "default": 24.0, "label": "Tw ≤ °C"}],
        ),
        PushConditionTypeInfo(
            type="pressure_stable", label="Стабильное давление",
            params_schema=[{"name": "delta_max", "kind": "number", "min": 0.5, "max": 15.0, "step": 0.5, "default": 4.0, "label": "|ΔP/24h| ≤ hPa"}],
        ),
        PushConditionTypeInfo(
            type="cloud_max", label="Не слишком облачно",
            params_schema=[{"name": "pct", "kind": "number", "min": 0.0, "max": 100.0, "step": 5.0, "default": 70.0, "label": "облачность ≤ %"}],
        ),
        PushConditionTypeInfo(
            type="daylight_min", label="Длинный световой день",
            params_schema=[{"name": "hours", "kind": "number", "min": 6.0, "max": 20.0, "step": 0.5, "default": 12.0, "label": "часов ≥"}],
        ),
        PushConditionTypeInfo(
            type="lookahead_max_days", label="В ближайшие N дней",
            params_schema=[{"name": "days", "kind": "integer", "min": 1, "max": 7, "step": 1, "default": 3, "label": "не дальше чем"}],
        ),
        PushConditionTypeInfo(type="weekend_only", label="Только в выходные"),
        PushConditionTypeInfo(
            type="moon_growing", label="Только растущая луна",
            params_schema=[{"name": "growing", "kind": "boolean", "default": True, "label": "растущая (true) / убывающая (false)"}],
        ),
        PushConditionTypeInfo(
            type="moon_phase_in", label="Фаза луны",
            params_schema=[{"name": "kinds", "kind": "multiselect", "default": "full",
                "label": "включает фазы",
                "options": ["new", "waxing_crescent", "first_quarter", "waxing_gibbous",
                            "full", "waning_gibbous", "last_quarter", "waning_crescent"]}],
        ),
    ]
    return PushConditionTypesResponse(types=types)


@app.post("/v1/push/subscriptions", response_model=PushSubscriptionRecord, status_code=status.HTTP_201_CREATED)
async def push_subscribe(
    payload: PushSubscriptionCreate,
    auth_user: AuthUser = Depends(get_current_user),
) -> PushSubscriptionRecord:
    if not push_service.enabled:
        raise ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="PUSH_DISABLED",
            message="push notifications not configured (no VAPID keys)",
            retryable=False,
        )
    conditions = [c.model_dump() for c in payload.conditions]
    sub = push_repository.upsert(
        user_id=auth_user.user_id,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth_secret=payload.keys.auth,
        name=payload.name,
        scope_zone=payload.scope_zone or None,
        scope_species=payload.scope_species,
        conditions=conditions,
    )
    logger.info(
        "push_subscription_upserted",
        extra={
            "event_type": "push_subscribe",
            "user_id": auth_user.user_id,
            "scope_zone": sub.scope_zone,
            "scope_species": sub.scope_species,
            "conditions_count": len(sub.conditions),
            "sub_id": sub.id,
        },
    )
    return _sub_to_record(sub)


@app.get("/v1/push/subscriptions/me", response_model=list[PushSubscriptionRecord])
async def push_subscriptions_me(
    auth_user: AuthUser = Depends(get_current_user),
) -> list[PushSubscriptionRecord]:
    subs = push_repository.list_by_user(auth_user.user_id)
    return [_sub_to_record(s) for s in subs]


def _sub_to_record(sub) -> PushSubscriptionRecord:
    return PushSubscriptionRecord(
        id=sub.id, user_id=sub.user_id, endpoint=sub.endpoint,
        name=sub.name, scope_zone=sub.scope_zone, scope_species=sub.scope_species,
        conditions=sub.conditions,
        last_notified_for_day=sub.last_notified_for_day,
        created_at=sub.created_at, updated_at=sub.updated_at,
    )


@app.delete("/v1/push/subscriptions/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
async def push_unsubscribe(
    sub_id: str,
    auth_user: AuthUser = Depends(get_current_user),
) -> None:
    deleted = push_repository.delete(sub_id=sub_id, user_id=auth_user.user_id)
    if not deleted:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="PUSH_SUB_NOT_FOUND",
            message="subscription not found",
            retryable=False,
        )
    return None


@app.post("/v1/push/test")
async def push_test(auth_user: AuthUser = Depends(get_current_user)) -> dict:
    if not push_service.enabled:
        raise ApiError(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="PUSH_DISABLED", message="push not configured", retryable=False,
        )
    subs = push_repository.list_by_user(auth_user.user_id)
    if not subs:
        return {"status": "no_subscription"}
    sub = subs[0]
    ok = push_service.send(
        sub=sub,
        title="🎣 Тестовое уведомление",
        body="Push-уведомления работают. Хорошего клёва!",
        data={"test": True},
    )
    return {"status": "ok" if ok else "failed", "sub_id": sub.id}


@app.post("/auth/login", response_model=LoginResponse)
@app.post("/v1/auth/login", response_model=LoginResponse)
async def auth_login(payload: LoginRequest) -> LoginResponse:
    return authenticate_demo_user(payload, settings)


@app.post("/v1/admin/ingest/weather")
async def ingest_weather(auth_user: AuthUser = Depends(get_current_user)) -> dict:
    result: WeatherIngestResult = weather_ingest_service.ingest_daily_forecast()
    forecast_cache.delete_many(FORECAST_CACHE_KEYS)
    # Best-effort water level refresh — never fails the weather ingest.
    water_level_ingest_outcome: dict | None = None
    try:
        wl_result = water_level_ingest_service.ingest()
        water_level_ingest_outcome = {
            "status": wl_result.status,
            "reason": wl_result.reason,
            "saved": (
                {"day": str(wl_result.saved.day), "level_m": wl_result.saved.level_m, "source": wl_result.saved.source}
                if wl_result.saved
                else None
            ),
        }
    except Exception:
        logger.exception("water_level_ingest_failed_in_weather_ingest")
        water_level_ingest_outcome = {"status": "error", "reason": "exception (see logs)"}
    # Dispatch push notifications best-effort. Each subscription gets a
    # notification when its zone+species forecast meets the threshold,
    # deduplicated by last_notified_for_day. Disabled silently if no
    # VAPID keys are configured.
    push_outcome: dict | None = None
    today = datetime.now(UTC).date()
    water_state = water_level_service.current_state(today=today)
    water_level_context = WaterLevelContext(
        latest_level_m=water_state.latest_level_m,
        trend_7d_m=water_state.trend_7d_m,
        source=water_state.source,
        is_fresh=water_state.is_fresh,
    )

    def _snapshots_for_zone(zone_code):
        if zone_code:
            zone_snapshots = weather_repository.get_window(start_day=today, days=7, zone=zone_code)
            if len(zone_snapshots) >= 7:
                return zone_snapshots
        return weather_repository.get_window(start_day=today, days=7, zone="default")

    try:
        if push_service.enabled:
            outcome = push_service.dispatch_for_all(
                snapshots_loader=_snapshots_for_zone,
                water_level=water_level_context,
            )
            push_outcome = {
                "sent": outcome.sent,
                "skipped_no_match": outcome.skipped_no_match,
                "skipped_duplicate": outcome.skipped_duplicate,
                "failed": outcome.failed,
                "expired_pruned": outcome.expired_pruned,
            }
        else:
            push_outcome = {"status": "disabled"}
    except Exception:
        logger.exception("push_dispatch_failed_in_weather_ingest")
        push_outcome = {"status": "error"}

    logger.info(
        "weather_ingest_completed",
        extra={
            "event_type": "weather_ingest",
            "rows": result.rows,
            "source": result.source,
            "requested_by": auth_user.user_id,
            "water_level_outcome": water_level_ingest_outcome.get("status") if water_level_ingest_outcome else None,
            "push_outcome": push_outcome,
        },
    )
    return {
        "status": "ok",
        "rows": result.rows,
        "source": result.source,
        "fetched_at": result.fetched_at,
        "zones": result.zones,
        "water_level": water_level_ingest_outcome,
        "push": push_outcome,
    }


@app.post("/v1/admin/ingest/water-level")
async def ingest_water_level(auth_user: AuthUser = Depends(get_current_user)) -> dict:
    result = water_level_ingest_service.ingest()
    if result.status == "ok":
        forecast_cache.delete_many(FORECAST_CACHE_KEYS)
    logger.info(
        "water_level_ingest_completed",
        extra={
            "event_type": "water_level_ingest",
            "status": result.status,
            "reason": result.reason,
            "requested_by": auth_user.user_id,
        },
    )
    return {
        "status": result.status,
        "reason": result.reason,
        "saved": (
            {
                "day": str(result.saved.day),
                "level_m": result.saved.level_m,
                "source": result.saved.source,
            }
            if result.saved
            else None
        ),
    }


@app.get("/v1/admin/dq/weather")
async def weather_dq(auth_user: AuthUser = Depends(get_current_user)) -> dict:
    result: WeatherQualityResult = weather_quality_service.run_checks()
    if result.status != "ok":
        logger.warning(
            "weather_dq_degraded",
            extra={
                "event_type": "weather_dq",
                "requested_by": auth_user.user_id,
                "checks": result.checks,
            },
        )
    return {
        "status": result.status,
        "checks": result.checks,
    }


@app.post("/v1/admin/water-level", response_model=WaterLevelResponse, status_code=status.HTTP_201_CREATED)
async def record_water_level(
    payload: WaterLevelCreate,
    auth_user: AuthUser = Depends(get_current_user),
) -> WaterLevelResponse:
    saved = water_level_repository.upsert(
        WaterLevelReading(
            day=payload.day,
            level_m=payload.level_m,
            inflow_m3s=payload.inflow_m3s,
            outflow_m3s=payload.outflow_m3s,
            source=payload.source,
            note=payload.note,
        )
    )
    forecast_cache.delete_many(FORECAST_CACHE_KEYS)
    logger.info(
        "water_level_recorded",
        extra={
            "event_type": "water_level_record",
            "requested_by": auth_user.user_id,
            "day": str(saved.day),
            "level_m": saved.level_m,
            "source": saved.source,
        },
    )
    assert saved.recorded_at is not None
    return WaterLevelResponse(
        day=saved.day,
        level_m=saved.level_m,
        inflow_m3s=saved.inflow_m3s,
        outflow_m3s=saved.outflow_m3s,
        source=saved.source,
        note=saved.note,
        recorded_at=saved.recorded_at,
    )


@app.get("/v1/admin/water-level/latest", response_model=WaterLevelStateResponse)
async def water_level_latest(auth_user: AuthUser = Depends(get_current_user)) -> WaterLevelStateResponse:
    state = water_level_service.current_state()
    return WaterLevelStateResponse(
        latest_level_m=state.latest_level_m,
        latest_day=state.latest_day,
        trend_7d_m=state.trend_7d_m,
        source=state.source,
        is_fresh=state.is_fresh,
    )


@app.post("/v1/admin/ml/retrain")
async def ml_retrain(auth_user: AuthUser = Depends(get_current_user)) -> dict:
    result: RetrainResult = ml_service.retrain()
    if result.status == "ok":
        forecast_cache.delete_many(FORECAST_CACHE_KEYS)
    logger.info(
        "ml_retrain_finished",
        extra={
            "event_type": "ml_retrain",
            "requested_by": auth_user.user_id,
            "status": result.status,
            "reason": result.reason,
        },
    )
    return {
        "status": result.status,
        "reason": result.reason,
        "model": result.model,
    }


@app.get("/v1/admin/ml/latest")
async def ml_latest(auth_user: AuthUser = Depends(get_current_user)) -> dict:
    model = ml_service.latest_model()
    return {
        "status": "ok",
        "model": model,
    }


@app.get("/v1/admin/ml/active")
async def ml_active(auth_user: AuthUser = Depends(get_current_user)) -> dict:
    model = ml_service.active_model()
    return {
        "status": "ok",
        "model": model,
    }


@app.post("/v1/admin/ml/publish")
async def ml_publish(model_id: str | None = None, auth_user: AuthUser = Depends(get_current_user)) -> dict:
    result: PublishResult = ml_service.publish_model(model_id=model_id)
    if result.status == "ok":
        forecast_cache.delete_many(FORECAST_CACHE_KEYS)
    logger.info(
        "ml_publish_finished",
        extra={
            "event_type": "ml_publish",
            "requested_by": auth_user.user_id,
            "status": result.status,
            "reason": result.reason,
            "model_id": result.model["id"] if result.model else None,
        },
    )
    return {
        "status": result.status,
        "reason": result.reason,
        "model": result.model,
    }


@app.post("/catch", response_model=CatchRecord, status_code=status.HTTP_201_CREATED)
@app.post("/v1/catch", response_model=CatchRecord, status_code=status.HTTP_201_CREATED)
async def post_catch(
    payload: CatchCreate,
    request: Request,
    auth_user: AuthUser = Depends(get_current_user),
) -> CatchRecord:
    source_ip = request.headers.get("x-forwarded-for", "")
    if not source_ip and request.client:
        source_ip = request.client.host
    source_ip = source_ip or "-"

    guard_result = catch_guard.allow_submission(user_id=auth_user.user_id, source_ip=source_ip, payload=payload)
    if not guard_result.allowed:
        if guard_result.reason == "rate_limited":
            _audit_catch_event(
                outcome="rejected",
                source_ip=source_ip,
                user_id=auth_user.user_id,
                species=payload.species,
                score=payload.score,
                latitude=payload.latitude,
                longitude=payload.longitude,
                reason="rate_limited",
            )
            raise ApiError(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                code="CATCH_RATE_LIMITED",
                message=f"rate limit exceeded, retry in {guard_result.retry_after_sec}s",
                retryable=True,
                details={"retry_after_sec": guard_result.retry_after_sec},
            )
        if guard_result.reason == "duplicate_submission":
            _audit_catch_event(
                outcome="rejected",
                source_ip=source_ip,
                user_id=auth_user.user_id,
                species=payload.species,
                score=payload.score,
                latitude=payload.latitude,
                longitude=payload.longitude,
                reason="duplicate_submission",
            )
            raise ApiError(
                status_code=status.HTTP_409_CONFLICT,
                code="CATCH_DUPLICATE_SUBMISSION",
                message="duplicate catch submission detected",
                retryable=False,
            )
    record = forecast_service.create_catch(payload, user_id=auth_user.user_id)
    _audit_catch_event(
        outcome="accepted",
        source_ip=source_ip,
        user_id=auth_user.user_id,
        species=payload.species,
        score=payload.score,
        latitude=payload.latitude,
        longitude=payload.longitude,
        catch_id=record.id,
    )
    return record


@app.put("/v1/consent", response_model=ConsentRecord)
async def upsert_consent(payload: ConsentUpdate, auth_user: AuthUser = Depends(get_current_user)) -> ConsentRecord:
    record = consent_repository.upsert(user_id=auth_user.user_id, payload=payload, updated_at=utcnow())
    logger.info(
        "consent_updated",
        extra={
            "event_type": "consent_update",
            "user_id": auth_user.user_id,
            "geo_allowed": record.geo_allowed,
            "push_allowed": record.push_allowed,
            "analytics_allowed": record.analytics_allowed,
        },
    )
    return record


@app.get("/v1/consent/me", response_model=ConsentRecord)
async def get_consent(auth_user: AuthUser = Depends(get_current_user)) -> ConsentRecord:
    record = consent_repository.get(auth_user.user_id)
    if record is None:
        return ConsentRecord(
            user_id=auth_user.user_id,
            geo_allowed=False,
            push_allowed=False,
            analytics_allowed=False,
            updated_at=utcnow(),
        )
    return record


@app.delete("/v1/me/data", response_model=DeleteMeDataResponse)
async def delete_me_data(auth_user: AuthUser = Depends(get_current_user)) -> DeleteMeDataResponse:
    deleted_catches = catch_repository.delete_by_user_id(auth_user.user_id)
    deleted_consent = consent_repository.delete(auth_user.user_id)
    result = DeleteMeDataResponse(
        status="ok",
        user_id=auth_user.user_id,
        deleted_catches=deleted_catches,
        deleted_consent=deleted_consent,
        processed_at=utcnow(),
    )
    logger.warning(
        "user_data_deleted",
        extra={
            "event_type": "user_data_delete",
            "user_id": auth_user.user_id,
            "deleted_catches": deleted_catches,
            "deleted_consent": deleted_consent,
        },
    )
    return result


@app.get("/v1/me/data", response_model=MeDataExportResponse)
async def export_me_data(auth_user: AuthUser = Depends(get_current_user)) -> MeDataExportResponse:
    catches = catch_repository.list_by_user_id(auth_user.user_id)
    consent = consent_repository.get(auth_user.user_id)
    result = MeDataExportResponse(
        status="ok",
        user_id=auth_user.user_id,
        catches=catches,
        consent=consent,
        exported_at=utcnow(),
    )
    logger.info(
        "user_data_exported",
        extra={
            "event_type": "user_data_export",
            "user_id": auth_user.user_id,
            "catch_rows": len(catches),
            "has_consent": consent is not None,
        },
    )
    return result
