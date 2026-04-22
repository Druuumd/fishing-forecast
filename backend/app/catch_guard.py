import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC

from redis import Redis

from app.schemas import CatchCreate

logger = logging.getLogger("fishing_forecast.catch_guard")


@dataclass(frozen=True)
class CatchGuardResult:
    allowed: bool
    reason: str | None = None
    retry_after_sec: int | None = None


class CatchGuard:
    def __init__(
        self,
        redis_client: Redis,
        rate_limit_window_sec: int,
        rate_limit_max_requests: int,
        duplicate_window_sec: int,
    ) -> None:
        self._redis = redis_client
        self._rate_limit_window_sec = rate_limit_window_sec
        self._rate_limit_max_requests = rate_limit_max_requests
        self._duplicate_window_sec = duplicate_window_sec

    def allow_submission(self, user_id: str, source_ip: str, payload: CatchCreate) -> CatchGuardResult:
        if not self._allow_rate_limit(user_id=user_id):
            return CatchGuardResult(
                allowed=False,
                reason="rate_limited",
                retry_after_sec=self._rate_limit_window_sec,
            )

        if self._is_duplicate(user_id=user_id, source_ip=source_ip, payload=payload):
            return CatchGuardResult(
                allowed=False,
                reason="duplicate_submission",
                retry_after_sec=self._duplicate_window_sec,
            )

        return CatchGuardResult(allowed=True)

    def _allow_rate_limit(self, user_id: str) -> bool:
        key = f"catch:rl:{user_id}"
        try:
            current = self._redis.incr(key)
            if current == 1:
                self._redis.expire(key, self._rate_limit_window_sec)
            return current <= self._rate_limit_max_requests
        except Exception:
            logger.exception("catch_rate_limit_check_failed", extra={"user_id": user_id})
            # fail-open: do not block catch submission when Redis is degraded
            return True

    def _is_duplicate(self, user_id: str, source_ip: str, payload: CatchCreate) -> bool:
        caught_at = payload.caught_at.astimezone(UTC).isoformat() if payload.caught_at else "none"
        dedupe_material = "|".join(
            [
                user_id,
                source_ip,
                payload.species,
                f"{payload.score:.2f}",
                f"{payload.latitude:.4f}",
                f"{payload.longitude:.4f}",
                (payload.note or "").strip().lower(),
                caught_at,
            ]
        )
        fingerprint = hashlib.sha256(dedupe_material.encode("utf-8")).hexdigest()
        key = f"catch:dup:{fingerprint}"
        try:
            was_set = self._redis.set(key, "1", ex=self._duplicate_window_sec, nx=True)
            return not bool(was_set)
        except Exception:
            logger.exception("catch_duplicate_check_failed", extra={"user_id": user_id})
            # fail-open: skip duplicate rejection when Redis is degraded
            return False
