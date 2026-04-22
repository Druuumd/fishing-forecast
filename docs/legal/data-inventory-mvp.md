# Data Inventory (MVP)

Дата обновления: 2026-04-21

## 1) Категории данных и хранилища
- **Auth/identity (минимум MVP)**:
  - источник: `POST /v1/auth/login` (demo auth),
  - хранение: JWT claims (краткоживущие), app logs.
- **Catch records**:
  - поля: species/score/coords/caught_at/note + linked weather,
  - хранение: PostgreSQL (`catch_records`).
- **Weather snapshots**:
  - поля: air/pressure/water/moon/source/fetched_at,
  - хранение: PostgreSQL (`weather_snapshots`).
- **ML metadata**:
  - поля: model versions, metrics, publish state,
  - хранение: PostgreSQL (`ml_model_versions`).
- **User consent**:
  - поля: geo/push/analytics flags,
  - хранение: PostgreSQL (`user_consents`).
- **Operational logs**:
  - trace/request, audit events, errors,
  - хранение: stdout/log sink хоста.
- **Cache/guard keys**:
  - forecast cache, rate-limit, dedupe keys,
  - хранение: Redis (TTL-базированное).

## 2) Доступ к данным
- Доступ приложения: контейнер `api` (service account appuser).
- Админ-доступ инфраструктуры: владелец хоста `fazendaserv`/операторы.
- Клиентский доступ пользователя: только через bearer auth (`/v1/*`).

## 3) Retention и удаление
- Backup БД: 30 дней (cron policy).
- Redis ключи: TTL согласно настройкам (`FORECAST_CACHE_TTL_SEC`, guard windows).
- DSAR self-service:
  - экспорт: `GET /v1/me/data`
  - удаление: `DELETE /v1/me/data`
- Логи и backup очищаются по retention-политикам.

## 4) Передача третьим сторонам
- Open-Meteo используется только для погодных данных.
- Персональные данные уловов во внешние weather API не отправляются.
