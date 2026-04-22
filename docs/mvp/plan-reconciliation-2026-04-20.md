# Сверка выполнения с исходным планом (2026-04-20)

## Источники сверки
- Исходный план: `docs/mvp/final-plan.md`
- Scope freeze: `FISHING_FORECAST_MVP_SCOPE_FREEZE.md`
- Текущий трек: `docs/mvp/ROADMAP.md`
- Фактические работы: `docs/ops/WORK_JOURNAL.md`

## Краткий итог
- **Фазы A-2:** в основном закрыты (foundation, infra, data layer, безопасность API и ops-база).
- **Фазы 3-4:** частично (API v1 и hardening готовы; ingestion/ML/mobile еще не начаты).
- **Фаза 5 (release/ops):** частично (backup/restore/rollback сделаны; legal и финальные quality gates не закрыты).

## Матрица: План -> Факт

### 1) Scope MVP (core backend)
- 7-дневный прогноз (`GET /forecast`) -> **выполнено** (`/v1/forecast` + legacy alias).
- Отправка уловов (`POST /catch`) -> **выполнено** (`/v1/catch`, валидация, привязка к weather snapshot, PostgreSQL).
- Базовая авторизация -> **выполнено** (JWT bearer через `/v1/auth/login`).

### 2) Infra / Server / Security baseline (Phase 1)
- Dockerized deployment -> **выполнено** (стек на `fazendaserv`).
- Health/readiness + structured logs + trace-id -> **выполнено**.
- Rate-limit + anti-spam + audit logs -> **выполнено**.
- Закрытие внутренних сервисов от внешнего доступа -> **выполнено** (`db/redis` internal-only).
- Security review хоста -> **выполнено условно** (есть отчет, часть пунктов `UNKNOWN` без root/sudo).

### 3) Data platform (Phase 2)
- PostgreSQL/Redis подключены -> **выполнено**.
- Миграции схемы БД -> **выполнено** (Alembic).
- Ingestion погоды/воды/луны + DQ checks -> **не выполнено**.

### 4) ML + API (Phase 3)
- API-контракт v1 -> **выполнено**.
- Offline-friendly error contract -> **выполнено**.
- Baseline ML, retrain policy, ML quality gates -> **не выполнено**.

### 5) Mobile readiness (Phase 4)
- Mobile integration examples -> **выполнено** (документированы).
- Реальный mobile-клиент (прогноз/журнал/карта/push/offline queue) -> **не выполнено**.

### 6) Release & operations (Phase 5)
- Daily backup БД -> **выполнено** (cron 03:00, retention 30d).
- Restore drill -> **выполнено** (отчет есть).
- Rollback rehearsal -> **выполнено** (отчет есть).
- Legal minimum pack -> **не выполнено**.
- Внешняя доступность через WAN endpoint -> **не выполнено** (нет доступа к роутеру/NAT проверкам).
- Финальные quality gates GO -> **не выполнено**.

## Отклонения от раннего ТЗ
- В раннем ТЗ для `POST /catch` фигурировал `x-user-id`; фактически реализована более корректная схема bearer JWT.
- Это **улучшение безопасности** и соответствует цели "базовая авторизация" из исходного плана.

## Остаток до MVP по плану
1. Data ingestion + DQ pipeline (погода/вода/луна).
2. Baseline ML + retrain + quality metrics.
3. Mobile implementation (минимальный клиентский контур MVP).
4. Legal minimum pack (policy/terms/deletion).
5. WAN endpoint readiness (после доступа к роутеру).
6. Финальный прогон quality gates и решение GO/NO-GO.
