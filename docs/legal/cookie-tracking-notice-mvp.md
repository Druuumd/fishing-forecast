# Cookie & Tracking Notice (MVP)

Дата обновления: 2026-04-21

## Контур MVP
- Публичный контур MVP — API-first backend.
- На API-уровне cookie для auth/сессий не используются (bearer token в `Authorization` заголовке).

## Tracking в MVP
- Сервер ведет технические логи запросов (`trace_id`, `status_code`, `path`, `elapsed_ms`) для observability и безопасности.
- Отдельные пользовательские web-tracking cookie в текущем MVP не применяются.

## Что будет при появлении web/admin UI
- Перед включением web-tracking/cookies будет обновлен этот документ.
- В UI будет добавлен баннер/настройки согласий на tracking.
