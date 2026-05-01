# KVH Forecast — API Reference

*Обновлено: 2026-04-27*

Все endpoint-ы под префиксом `/v1/`. Public-эндпоинты не требуют
аутентификации (read-only data). Admin-эндпоинты требуют
`Authorization: Bearer <token>`. POST `/v1/catch` и push subscribe
тоже требуют токен.

**Базовые URL**:
* Production: `https://kvh-forecast.ru`
* Stage / dev: `http://192.168.0.250:8000` (только из LAN)

**Формат ответа**: JSON, charset UTF-8. Время в ISO 8601 UTC с `Z` или
`+00:00` (Pydantic).

**Формат ошибки**:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "human-readable description",
    "retryable": false,
    "request_id": "uuid",
    "details": { "field_errors": { ... } }
  }
}
```

---

## 1. Health

### GET /v1/health

Liveness — отвечает всегда если процесс жив.
```bash
curl -sk https://kvh-forecast.ru/v1/health
# {"status":"ok"}
```

### GET /v1/ready

Readiness — проверяет DB и Redis.
```bash
curl -sk https://kvh-forecast.ru/v1/ready
# {"status":"ready","env":"stage","db":"up","redis":"up"}
```

`status_code` = 503 если db не в порядке.

---

## 2. Аутентификация

### POST /v1/auth/login

```bash
curl -sk -X POST https://kvh-forecast.ru/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"demo123"}'
```

Ответ:
```json
{"access_token": "eyJhbGc...", "expires_at": "2026-04-27T22:00:00Z"}
```

JWT действителен `auth_access_token_expire_min=120` минут.

---

## 3. Прогноз

### GET /v1/forecast

Параметры:
* `species` (опционально) — `pike`, `perch` или `bream`. Без параметра возвращает все три.
* `zone` (опционально) — код залива (см. `/v1/zones/centers`). Без параметра — обзорный режим.

```bash
curl -sk 'https://kvh-forecast.ru/v1/forecast?species=pike&zone=biryusa' | jq .
```

Сокращённый ответ:
```json
{
  "generated_at": "2026-04-27T15:00:00Z",
  "last_updated_at": "2026-04-27T03:15:22Z",
  "water_level_m": 228.41,
  "water_level_trend_7d_m": -0.46,
  "water_level_source": "manual",
  "water_level_is_fresh": true,
  "zone": "biryusa",
  "zone_label": "Бирюсинский залив (р. Бирюса)",
  "days": [
    {
      "date": "2026-04-27",
      "species": "pike",
      "score": 1.78,
      "confidence": 0.62,
      "air_temp_c": 7.5,
      "pressure_hpa": 1019.7,
      "surface_pressure_hpa": 991.2,
      "pressure_trend_24h_hpa": 6.9,
      "pressure_trend_6h_hpa": 1.7,
      "water_temp_c": 2.7,
      "wind_speed_m_s": 3.5,
      "wind_direction_deg": 230.0,
      "moon_phase": 0.22,
      "moon_age_days": 6.5,
      "moon_illumination_pct": 40.6,
      "moon_phase_kind": "first_quarter",
      "moon_phase_label": "Первая четверть",
      "moon_growing": true,
      "cloud_cover_pct": 56.0,
      "precipitation_mm": 0.0,
      "humidity_pct": 80.0,
      "daylight_hours": 14.9,
      "sunrise": "2026-04-26T22:13:00Z",
      "sunset": "2026-04-27T13:18:00Z",
      "water_level_m": 228.41,
      "water_level_trend_7d_m": -0.46,
      "water_level_source": "manual",
      "zone": "biryusa",
      "zone_label": "Бирюсинский залив (р. Бирюса)",
      "thermocline_strength": 0.0,
      "thermocline_depth_m": null,
      "thermocline_recommended_depth_m": null,
      "thermocline_advice": "Вода перемешана — ловите по рельефу дна.",
      "best_hours": [
        { "start": "...", "end": "...", "label": "Утренняя зорька", "kind": "dawn", "intensity": 1.0 },
        { "start": "...", "end": "...", "label": "Лунный зенит", "kind": "lunar_major", "intensity": 0.83 }
      ],
      "stale": false,
      "factors": [
        { "name": "base", "contribution": 2.8, "detail": null },
        { "name": "water_temp", "contribution": 0.088, "detail": "2.7°C (opt 10°C)" },
        { "name": "pressure", "contribution": 0.121, "detail": "1020 hPa MSL → 991 hPa surface@234m" },
        { "name": "pressure_shock_gate", "contribution": -0.677, "detail": "ΔP24h=+6.9 hPa (sharp rise) (×0.71)" }
      ]
    }
  ]
}
```

Кеш: forecast_cache_ttl_sec=300 (5 минут). Кеш-ключ включает (zone,
species), очищается при ingest weather, при upsert уровня и при
ML retrain.

### GET /v1/warnings

Активные adverse-conditions.

Параметры:
* `zone` (опционально) — фильтр зоны.

```bash
curl -sk https://kvh-forecast.ru/v1/warnings | jq .
```

```json
{
  "generated_at": "2026-04-27T15:00:00Z",
  "zone": null,
  "zone_label": null,
  "warnings": [
    {
      "code": "pressure_shock",
      "severity": "warn",
      "title": "Резкий скачок давления",
      "body": "Барический шок в ближайшие дни (от 2026-04-28). ...",
      "valid_from": "2026-04-28",
      "valid_to": "2026-04-28"
    },
    {
      "code": "spawning_ban",
      "severity": "info",
      "title": "Нерестовый запрет",
      "body": "Действует нерестовый запрет на Красноярском водохранилище ...",
      "valid_from": "2026-04-25",
      "valid_to": "2026-06-25"
    }
  ]
}
```

Severity: `danger` (физически опасно или запрещено), `warn` (испортит
выезд), `info` (контекстно).

10 типов кодов: `pressure_shock`, `severe_weather`, `gale_wind`,
`heavy_rain`, `ice_unsafe`, `drawdown_alarm`, `spawning_ban`,
`pike_spawning`, `perch_spawning`, `bream_spawning`.

### GET /v1/zones/centers

Координаты + label всех 13 заливов (для карты).

```bash
curl -sk https://kvh-forecast.ru/v1/zones/centers | jq '.zones[0]'
```

```json
{
  "code": "syda",
  "label": "Сыдинский залив (р. Сыда)",
  "lat": 54.55,
  "lon": 91.5,
  "archetype": "shallow_warm"
}
```

---

## 4. История

### GET /v1/water-level/history

Параметры:
* `days` — количество дней в окне (default 30, max 365).

```bash
curl -sk 'https://kvh-forecast.ru/v1/water-level/history?days=14' | jq .
```

```json
{
  "days_requested": 14,
  "points": [
    {"day": "2026-04-13", "level_m": 230.45, "source": "backfill-seed"},
    ...
  ],
  "npu_m": 243.0,
  "umo_m": 225.0
}
```

`npu_m`/`umo_m` — refs для UI чартов.

### GET /v1/weather/history

Параметры:
* `days` (default 14, max 60).

```bash
curl -sk 'https://kvh-forecast.ru/v1/weather/history?days=7' | jq '.points[0]'
```

```json
{
  "day": "2026-04-21",
  "air_temp_c": -2.0,
  "pressure_hpa": 1021.9,
  "surface_pressure_hpa": 992.3,
  "water_temp_c": 3.1,
  "wind_speed_m_s": 2.1,
  "cloud_cover_pct": 0.0,
  "precipitation_mm": 0.0,
  "pressure_trend_24h_hpa": 0.0
}
```

---

## 5. Уровень воды

### POST /v1/admin/water-level (auth required)

Внести замер.

```bash
curl -sk -X POST https://kvh-forecast.ru/v1/admin/water-level \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "day": "2026-04-27",
    "level_m": 228.5,
    "inflow_m3s": 1500.0,
    "outflow_m3s": 1450.0,
    "source": "manual",
    "note": "daily check at dam"
  }'
```

`inflow_m3s` / `outflow_m3s` опциональны.

Ответ — `WaterLevelResponse` с `recorded_at` (когда сохранили).

### GET /v1/admin/water-level/latest (auth required)

Текущий aggregate state — что использует scoring.

```json
{
  "latest_level_m": 228.5,
  "latest_day": "2026-04-27",
  "trend_7d_m": -0.91,
  "source": "manual",
  "is_fresh": true
}
```

`is_fresh` = false когда последний replay старше 14 дней (тогда
`source` будет `climatology`).

### POST /v1/admin/ingest/water-level (auth required)

Триггер scraper-а вручную. См. `WATER_LEVEL_SCRAPE_*` env.

```json
{
  "status": "no_data",
  "reason": "source returned None",
  "saved": null
}
```

Возможные `status`: `ok`, `no_source` (scraping disabled), `no_data`
(source returned None), `stale_observation` (DB has fresher), `error`.

---

## 6. Замеры воды (crowdsourced)

### POST /v1/water-temp-readings (auth required)

Внести замер теплового профиля.

```bash
curl -sk -X POST https://kvh-forecast.ru/v1/water-temp-readings \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "measured_at": "2026-04-27T15:00:00Z",
    "latitude": 55.55,
    "longitude": 92.50,
    "surface_temp_c": 4.2,
    "thermocline_depth_m": 7.0,
    "below_thermocline_temp_c": 3.0,
    "instrument": "Garmin Striker 4",
    "note": "у мыса Бирюса"
  }'
```

Валидация:
* `latitude` ∈ [53.0, 56.0], `longitude` ∈ [90.5, 93.5] (bbox КВХ)
* `surface_temp_c` ∈ [0, 30]
* `thermocline_depth_m` ∈ [1, 60] (опционально)
* `below_thermocline_temp_c` ∈ [1, 10] (опционально, **строго ниже** surface)
* `measured_at` ≤ now+5min, ≥ now-30 days
* depth и below_temp задаются вместе или ни один (partial profile rejected)

При невалидных данных — 422:
```json
{
  "error": {
    "code": "WATER_TEMP_READING_INVALID",
    "message": "Замер не прошёл валидацию.",
    "retryable": false,
    "details": {
      "field_errors": {
        "below_thermocline_temp_c": "Температура под термоклином не может быть выше поверхностной."
      }
    }
  }
}
```

`zone` определяется автоматически (haversine до ближайшего bay-center
≤25 км, иначе `main_channel`).

### GET /v1/water-temp-readings

Public read для визуализации на карте.

Параметры:
* `zone` (опционально) — фильтр по zone code
* `limit` (default 100, max 500)
* `days` (default 30, max 60)

```bash
curl -sk 'https://kvh-forecast.ru/v1/water-temp-readings?zone=syda&days=7' | jq '.points'
```

---

## 7. Уловы

### POST /v1/catch (auth required)

Зарегистрировать улов.

```bash
curl -sk -X POST https://kvh-forecast.ru/v1/catch \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "species": "pike",
    "score": 4.5,
    "latitude": 55.0,
    "longitude": 91.7,
    "note": "two pike on jerkbait, 06:00",
    "caught_at": "2026-04-27T03:00:00Z"
  }'
```

`caught_at` опционален (default — now). При записи `forecast_service`
автоматически прикрепляет погодные параметры на дату из ближайшего
weather snapshot — это `linked_*` поля в ответе. Они потом используются
для ML retrain (correlation между моделью и реальностью).

Rate limiting: `catch_rate_limit_max_requests=10` за `catch_rate_limit_window_sec=60`.
Дубль-детектор по `caught_at` ± `catch_duplicate_window_sec=180`.

При rate limit:
```json
{
  "error": {
    "code": "CATCH_RATE_LIMITED",
    "message": "rate limit exceeded, retry in 30s",
    "retryable": true,
    "details": {"retry_after_sec": 30}
  }
}
```
HTTP 429 + `Retry-After` header.

При дубле:
```json
{
  "error": {"code": "CATCH_DUPLICATE_SUBMISSION", "message": "..."}
}
```
HTTP 409.

---

## 8. Push-уведомления

### GET /v1/push/vapid-public-key

Публичный VAPID ключ. Браузер использует его в `pushManager.subscribe()`.

```json
{
  "public_key": "BNJXe1Z3ahoI9HVMIlg15tOvuVGU5Px323HNgvGG__Jv0vMKkxZbcpn3VshYu6PMG9-t_oP51YsB2P30AgU3h1s",
  "enabled": true
}
```

`enabled: false` — VAPID не настроен на сервере, push отключён.

### GET /v1/push/condition-types

Каталог 15 типов условий с параметрами для UI-конструктора.

```json
{
  "types": [
    {
      "type": "score_min",
      "label": "Минимальная оценка",
      "params_schema": [
        {"name": "min", "kind": "number", "min": 0.0, "max": 5.0, "step": 0.1, "default": 3.5, "label": "оценка ≥"}
      ]
    },
    { "type": "no_pressure_shock", "label": "Без барического шока", "params_schema": [] },
    ...
  ]
}
```

### POST /v1/push/subscriptions (auth required)

Создать или обновить подписку.

```bash
curl -sk -X POST https://kvh-forecast.ru/v1/push/subscriptions \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "endpoint": "https://fcm.googleapis.com/fcm/send/...",
    "keys": {"p256dh": "BO...", "auth": "yy..."},
    "name": "лещ на Сыде в выходные",
    "scope_zone": "syda",
    "scope_species": "bream",
    "conditions": [
      {"type": "score_min", "params": {"min": 3.0}},
      {"type": "no_pressure_shock", "params": {}},
      {"type": "weekend_only", "params": {}}
    ]
  }'
```

При повторном POST с тем же `endpoint` — обновление (upsert).

### GET /v1/push/subscriptions/me (auth required)

Список подписок текущего юзера.

### DELETE /v1/push/subscriptions/{sub_id} (auth required)

204 при успехе, 404 если не найдена / не принадлежит юзеру.

### POST /v1/push/test (auth required)

Отправить тестовое уведомление на первую подписку юзера. Полезно
для верификации что VAPID + endpoint живы.

```json
{"status": "ok", "sub_id": "abc..."}
```

`status` ∈ `ok` / `failed` / `no_subscription`.

---

## 9. Соглашения и правовые

### GET /v1/legal/info

Контакты + ссылки на политики приватности и т.д. Используется
футером UI.

### GET /v1/consent/me (auth required)

Текущий consent юзера.

### PUT /v1/consent (auth required)

Обновить consent (geo, push, analytics flags).

### GET /v1/me/data (auth required)

DSAR — экспорт всех данных юзера: catches + consent.

### DELETE /v1/me/data (auth required)

DSAR — удалить все данные юзера (catches + consent). Returns
`deleted_catches` count и `deleted_consent` bool.

---

## 10. Admin

### POST /v1/admin/ingest/weather (auth required)

Триггер ingest pipeline:
1. Per-zone Open-Meteo fetch (5 calls: default + 4 named bays… + ещё 9)
2. temperaturavody.com scrape
3. Best-effort water-level scrape
4. Push dispatch (если есть свежие подписки)

Ответ:
```json
{
  "status": "ok",
  "rows": 126,
  "source": "open-meteo(fact+forecast)+temperaturavody-obs+temperaturavody-fc",
  "fetched_at": "2026-04-27T03:15:22Z",
  "zones": {"default": 9, "syda": 9, "derbino": 9, ...},
  "water_level": {"status": "no_source", "reason": "scraping disabled", "saved": null},
  "push": {"sent": 0, "skipped_no_match": 1, "skipped_duplicate": 0, "failed": 0, "expired_pruned": 0}
}
```

### GET /v1/admin/dq/weather (auth required)

Data-quality check.

```json
{
  "status": "ok",
  "checks": {
    "freshness": {"ok": true, "last_updated_at": "...", "age_hours": 0.01, "max_age_hours": 24},
    "completeness": {"ok": true, "rows": 7, "expected_rows": 7, "missing_days": []},
    "range": {"ok": true, "issues": []},
    "duplicates": {"ok": true, "unique_days": 7, "rows": 7}
  }
}
```

`status: "degraded"` если хоть одна проверка `ok: false`.

### POST /v1/admin/ml/retrain (auth required)

Запустить ML retrain. Skip-аются если `< ml_retrain_min_records`
(default 20) catch records в DB.

```json
{"status": "ok", "reason": null, "model": {"id": "...", "metrics": {...}}}
```

### GET /v1/admin/ml/active (auth required)

Активная (опубликованная) ML-модель.

### GET /v1/admin/ml/latest (auth required)

Последняя обученная (необязательно опубликованная).

### POST /v1/admin/ml/publish?model_id=… (auth required)

Опубликовать модель (auto-publish если smoke-test passed).

---

## 11. Trace ID

Все ответы содержат заголовок `X-Trace-Id` (UUID) — копируется во
входящий request если был, иначе генерируется новый. Используется для
correlation в логах:
```bash
docker compose logs api | grep <trace-id>
```

В body ошибки тот же id есть как `error.request_id`.

---

## 12. Cache layer (Redis)

Кешируются:
* `/v1/forecast?species=…&zone=…` — TTL 300 сек.
  Ключ: `forecast:v2:<zone_or_default>:<species_or_all>`

Кеш сбрасывается при:
* POST `/v1/admin/ingest/weather`
* POST `/v1/admin/water-level` (внесён замер)
* POST `/v1/admin/ingest/water-level` (если status=ok)
* POST `/v1/admin/ml/retrain` / `publish` (изменилась активная модель)
