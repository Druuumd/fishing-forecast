# Mobile Handoff Pack (2026-04-21)

Цель: передать mobile-команде полностью готовый backend-контракт и критерии приемки для закрытия финального release-блокера.

## 1) Backend scope (готово)
- Auth:
  - `POST /v1/auth/login`
- Forecast/Catch:
  - `GET /v1/forecast`
  - `POST /v1/catch`
- Consent:
  - `PUT /v1/consent`
  - `GET /v1/consent/me`
- DSAR:
  - `GET /v1/me/data` (export)
  - `DELETE /v1/me/data` (delete)
- Legal links/meta:
  - `GET /v1/legal/info`

## 2) UX flows to implement in mobile
- **Consent screen (first run/settings):**
  - toggle `geo_allowed`, `push_allowed`, `analytics_allowed`;
  - save via `PUT /v1/consent`;
  - initial state from `GET /v1/consent/me`.
- **DSAR screen (privacy/account):**
  - “Export my data” -> `GET /v1/me/data`;
  - “Delete my data” -> `DELETE /v1/me/data` + confirm dialog.
- **Legal links screen:**
  - privacy/terms/data-deletion/cookie URLs from `GET /v1/legal/info`;
  - контакты поддержки/приватности из того же endpoint.

## 3) Offline/retry policy
- Для `retryable=true` ошибки — очередь и retry с backoff.
- `401` (`AUTH_*`) — silent re-login + один повтор.
- `409 CATCH_DUPLICATE_SUBMISSION` — считать синхронизированным, без spam retry.
- Логировать `request_id` для диагностики.

## 4) API acceptance criteria for mobile
- Consent:
  - после `PUT /v1/consent` чтение `GET /v1/consent/me` возвращает те же флаги.
- DSAR export:
  - `GET /v1/me/data` возвращает `status=ok`, `user_id`, `catches[]`, `consent`.
- DSAR delete:
  - `DELETE /v1/me/data` возвращает `status=ok`;
  - последующий `GET /v1/me/data` возвращает пустой `catches[]` и `consent=null`/default.
- Legal:
  - `GET /v1/legal/info` возвращает production-значения `kvh-forecast.ru`.

## 5) Gate closure definition (mobile block)
Mobile release-блок считается закрытым, когда:
- согласия и DSAR UX доступны в приложении;
- выполнены тест-кейсы из `docs/mvp/mobile-beta-test-cases-2026-04-21.md`;
- нет P0/P1 дефектов по auth/forecast/catch/consent/dsar/legal-link flows.
