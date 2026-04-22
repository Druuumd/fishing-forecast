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
from app.forecast_service import ForecastService
from app.logging_config import configure_logging, new_trace_id, trace_id_ctx
from app.ml_repository import MlRepository
from app.ml_service import MlService, PublishResult, RetrainResult
from app.schemas import CatchCreate, CatchRecord, ConsentRecord, ConsentUpdate, FishSpecies, ForecastResponse, utcnow
from app.schemas import DeleteMeDataResponse, LegalInfoResponse, MeDataExportResponse
from app.settings import get_settings
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
)
weather_ingest_service = WeatherIngestService(settings, weather_repository)
weather_quality_service = WeatherQualityService(settings, weather_repository)
ml_service = MlService(settings, ml_repository, forecast_service)

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
async def get_forecast(species: FishSpecies | None = None) -> ForecastResponse:
    cache_key = f"forecast:v1:{species or 'all'}"
    cached_payload = forecast_cache.get(cache_key)
    if cached_payload:
        return ForecastResponse.model_validate_json(cached_payload)

    today = datetime.now(UTC).date()
    snapshots = weather_repository.get_window(start_day=today, days=7)
    last_updated_at = weather_repository.get_last_updated_at()
    is_fresh = False
    if last_updated_at is not None:
        freshness_deadline = datetime.now(UTC) - timedelta(hours=settings.forecast_freshness_hours)
        is_fresh = last_updated_at >= freshness_deadline

    active_model = ml_service.active_model()
    species_bias_map = active_model["species_bias"] if active_model else None

    if len(snapshots) >= 7 and is_fresh:
        response = forecast_service.build_forecast_from_snapshots(
            snapshots=snapshots[:7],
            species=species,
            stale=False,
            last_updated_at=last_updated_at,
            species_bias_map=species_bias_map,
        )
    else:
        response = forecast_service.build_forecast_from_snapshots(
            snapshots=forecast_service.default_snapshots(),
            species=species,
            stale=True,
            last_updated_at=last_updated_at,
            species_bias_map=species_bias_map,
        )
    forecast_cache.set(cache_key, response.model_dump_json())
    return response


@app.post("/auth/login", response_model=LoginResponse)
@app.post("/v1/auth/login", response_model=LoginResponse)
async def auth_login(payload: LoginRequest) -> LoginResponse:
    return authenticate_demo_user(payload, settings)


@app.post("/v1/admin/ingest/weather")
async def ingest_weather(auth_user: AuthUser = Depends(get_current_user)) -> dict:
    result: WeatherIngestResult = weather_ingest_service.ingest_daily_forecast()
    forecast_cache.delete_many(["forecast:v1:all", "forecast:v1:pike", "forecast:v1:perch"])
    logger.info(
        "weather_ingest_completed",
        extra={
            "event_type": "weather_ingest",
            "rows": result.rows,
            "source": result.source,
            "requested_by": auth_user.user_id,
        },
    )
    return {
        "status": "ok",
        "rows": result.rows,
        "source": result.source,
        "fetched_at": result.fetched_at,
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


@app.post("/v1/admin/ml/retrain")
async def ml_retrain(auth_user: AuthUser = Depends(get_current_user)) -> dict:
    result: RetrainResult = ml_service.retrain()
    if result.status == "ok":
        forecast_cache.delete_many(["forecast:v1:all", "forecast:v1:pike", "forecast:v1:perch"])
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
        forecast_cache.delete_many(["forecast:v1:all", "forecast:v1:pike", "forecast:v1:perch"])
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
