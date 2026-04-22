# Mobile Beta Test Cases (2026-04-21)

## Preconditions
- Backend stage доступен:
  - LAN: `http://192.168.0.250:8000`
  - WAN: `http://84.22.146.195:8000`
- Тестовый пользователь: `demo/demo123`.

## Test Cases

### TC-01 Login success
- Steps:
  1. Выполнить `POST /v1/auth/login` с валидными кредами.
- Expected:
  - `200`, есть `access_token`, `expires_at`.

### TC-02 Forecast rendering
- Steps:
  1. Выполнить `GET /v1/forecast?species=pike`.
- Expected:
  - `200`, минимум 7 записей.

### TC-03 Catch create
- Steps:
  1. Выполнить `POST /v1/catch` с bearer.
- Expected:
  - `201`, есть `id`.

### TC-04 Consent roundtrip
- Steps:
  1. `PUT /v1/consent` (например, `geo=true,push=false,analytics=false`);
  2. `GET /v1/consent/me`.
- Expected:
  - значения совпадают.

### TC-05 DSAR export
- Steps:
  1. `GET /v1/me/data`.
- Expected:
  - `200`, `status=ok`, корректный `user_id`, присутствуют `catches`/`consent`.

### TC-06 DSAR delete
- Steps:
  1. `DELETE /v1/me/data`;
  2. затем `GET /v1/me/data`.
- Expected:
  - удаление `status=ok`;
  - после удаления `catches=[]`, `consent` отсутствует/сброшен.

### TC-07 Legal links
- Steps:
  1. `GET /v1/legal/info`.
- Expected:
  - ссылки и email на домене `kvh-forecast.ru`.

### TC-08 Offline retry behavior
- Steps:
  1. Отключить сеть, отправить catch;
  2. включить сеть, выполнить retry.
- Expected:
  - запись из очереди уходит успешно;
  - без duplicate spam.
- Automation note:
  - В `scripts/run-mobile-beta-pass-fazendaserv.ps1` покрыт серверный replay-сценарий очереди (`Offline queue replay simulation`).
  - Полный airplane-mode UX проверяется вручную в `mobile-web`.

### TC-09 Auth expiry handling
- Steps:
  1. Использовать просроченный/битый токен в защищенном endpoint.
- Expected:
  - `401`, клиент делает relogin и повторяет запрос один раз.
- Automation note:
  - В `scripts/run-mobile-beta-pass-fazendaserv.ps1` покрыт flow `invalid token -> 401 -> relogin -> retry`.

## Exit Criteria
- Все TC-01..TC-09: PASS
- Нет P0/P1 багов.
