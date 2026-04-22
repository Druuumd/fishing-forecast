# Mobile Integration Examples (v1 API)

## Базовый flow авторизации и отправки улова
1. Логин:
   - `POST /v1/auth/login`
   - сохранить `access_token` и `expires_at`.
2. Прогноз:
   - `GET /v1/forecast?species=pike`
3. Отправка улова:
   - `POST /v1/catch` с `Authorization: Bearer <token>`.

## Пример запросов

### 1) Login
```http
POST /v1/auth/login
Content-Type: application/json

{
  "username": "demo",
  "password": "demo123"
}
```

### 2) Forecast
```http
GET /v1/forecast?species=perch
```

### 3) Catch
```http
POST /v1/catch
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "species": "perch",
  "score": 4.2,
  "latitude": 55.99,
  "longitude": 92.88,
  "note": "утренний выход"
}
```

### 4) Consent update
```http
PUT /v1/consent
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "geo_allowed": true,
  "push_allowed": false,
  "analytics_allowed": false
}
```

### 5) Consent read
```http
GET /v1/consent/me
Authorization: Bearer <access_token>
```

### 6) Delete my data (DSAR self-service API)
```http
DELETE /v1/me/data
Authorization: Bearer <access_token>
```

### 7) Export my data (DSAR access API)
```http
GET /v1/me/data
Authorization: Bearer <access_token>
```

### 8) Public legal info for app links
```http
GET /v1/legal/info
```

## Offline-friendly обработка ошибок

API возвращает единый формат ошибки:
```json
{
  "error": {
    "code": "CATCH_RATE_LIMITED",
    "message": "rate limit exceeded, retry in 60s",
    "retryable": true,
    "request_id": "trace-id-value",
    "details": {
      "retry_after_sec": 60
    }
  }
}
```

### Рекомендации по клиентской логике
- Если `retryable=true`, ставить событие в локальную очередь и повторять отправку по backoff.
- Если `code=CATCH_DUPLICATE_SUBMISSION`, считать запись синхронизированной (не спамить retry).
- Если `401` (`AUTH_*`), запускать silent re-login и повторять запрос один раз.
- Всегда логировать `request_id` в mobile crash/analytics для связи с серверными логами.

## Минимальная таблица кодов
- `AUTH_TOKEN_REQUIRED` (401): отсутствует bearer token.
- `AUTH_INVALID_TOKEN` (401): токен просрочен или невалиден.
- `AUTH_INVALID_CREDENTIALS` (401): неверные логин/пароль.
- `VALIDATION_ERROR` (422): невалидный payload.
- `CATCH_DUPLICATE_SUBMISSION` (409): дубликат события.
- `CATCH_RATE_LIMITED` (429): превышен лимит.
- `INTERNAL_ERROR` (500): серверная ошибка, retry допустим.
