from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Fishing Forecast API"
    app_env: str = "stage"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"
    log_format: str = "json"
    database_url: str = "postgresql://forecast:forecast@db:5432/forecast"
    redis_url: str = "redis://redis:6379/0"
    forecast_cache_ttl_sec: int = 300
    catch_rate_limit_window_sec: int = 60
    catch_rate_limit_max_requests: int = 10
    catch_duplicate_window_sec: int = 180
    auth_jwt_secret: str = "change_me_dev_secret"
    auth_jwt_algorithm: str = "HS256"
    auth_access_token_expire_min: int = 120
    auth_demo_user: str = "demo"
    auth_demo_password: str = "demo123"
    location_lat: float = 55.99
    location_lon: float = 92.88
    forecast_region: str = "krasnoyarsk"
    forecast_freshness_hours: int = 24
    ml_retrain_min_records: int = 20
    ml_smoke_max_mae: float = 1.0
    ml_smoke_max_rmse: float = 1.2
    ml_smoke_min_top_day_hit_rate: float = 0.3
    legal_contact_email: str = "privacy@kvh-forecast.ru"
    legal_support_email: str = "legal@kvh-forecast.ru"
    legal_privacy_url: str = "https://kvh-forecast.ru/privacy"
    legal_terms_url: str = "https://kvh-forecast.ru/terms"
    legal_data_deletion_url: str = "https://kvh-forecast.ru/data-deletion"
    legal_cookie_tracking_url: str = "https://kvh-forecast.ru/cookie-tracking"
    cors_allowed_origins: str = "https://kvh-forecast.ru,https://www.kvh-forecast.ru,http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
