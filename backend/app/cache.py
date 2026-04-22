import logging

from redis import Redis

from app.settings import Settings

logger = logging.getLogger("fishing_forecast.cache")


def create_redis_client(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


class ForecastCache:
    def __init__(self, redis_client: Redis, ttl_sec: int) -> None:
        self._redis = redis_client
        self._ttl_sec = ttl_sec

    def ping(self) -> bool:
        try:
            return bool(self._redis.ping())
        except Exception:
            return False

    def get(self, key: str) -> str | None:
        try:
            value = self._redis.get(key)
            if value:
                return value
            return None
        except Exception:
            logger.exception("forecast_cache_get_failed", extra={"cache_key": key})
            return None

    def set(self, key: str, payload: str) -> None:
        try:
            self._redis.setex(key, self._ttl_sec, payload)
        except Exception:
            logger.exception("forecast_cache_set_failed", extra={"cache_key": key})

    def delete_many(self, keys: list[str]) -> None:
        try:
            if keys:
                self._redis.delete(*keys)
        except Exception:
            logger.exception("forecast_cache_delete_failed", extra={"cache_keys": keys})
