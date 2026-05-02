from functools import lru_cache

from pydantic import field_validator
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
    # Median water-edge elevation above sea level (m).
    # Krasnoyarsk reservoir: UMO 226 m – NPU 243 m, median ~234 m.
    forecast_region_elevation_m: float = 234.0
    # Auto water-level scraping. Disabled by default until a verified
    # source is wired. Manual admin entry remains the authoritative
    # fallback. When enabled, weather ingest will best-effort attempt
    # to refresh the level; failures are logged but do not break ingest.
    water_level_scrape_enabled: bool = False
    water_level_scrape_source: str = "allrivers"
    water_level_scrape_page_url: str = "https://allrivers.info"
    water_level_scrape_gauge_id: int = 0
    water_level_scrape_timeout_sec: int = 15
    # Web Push (VAPID) — generated once via `python -m app.push_vapid`.
    # Keep both empty to disable push entirely (endpoints return 503).
    vapid_public_key_b64: str = ""
    vapid_private_key_pem: str = ""
    vapid_subject: str = "mailto:legal@kvh-forecast.ru"
    push_default_min_score: float = 3.5
    push_lookahead_days: int = 5
    # Spawning ban (нерестовый запрет) for Krasnoyarsk reservoir.
    # Per приказ Минсельхоза №226 от 13.05.2020 (Правила рыболовства
    # для Восточно-Сибирского рыбохозяйственного бассейна): для рек,
    # озёр и водохранилищ Красноярского края — с 25 апреля по 25 июня.
    # Operator can override via env if regulations are amended.
    spawning_ban_start_md: str = "04-25"   # MM-DD
    spawning_ban_end_md: str = "06-25"
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

    @field_validator("vapid_private_key_pem", mode="before")
    @classmethod
    def _normalize_pem(cls, v):
        # docker-compose env_file passes values as single-line strings.
        # Restore real newlines from literal \n and strip wrapping quotes
        # so the PEM ends up in the canonical multi-line format expected
        # by cryptography / pywebpush.
        if not isinstance(v, str):
            return v
        s = v.strip()
        if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
            s = s[1:-1]
        if "\\n" in s and "\n" not in s:
            s = s.replace("\\n", "\n")
        return s


@lru_cache
def get_settings() -> Settings:
    return Settings()
