# Roadmap и чеклист разработки (fazendaserv)

## Контекст
- Целевой хост серверной части: `fazendaserv` (`192.168.0.250`).
- Есть статический внешний IP роутера; внешний доступ к backend идет через него.
- Схема доступа: `external static IP (router)` -> `NAT/port-forward` -> `fazendaserv (192.168.0.250)`.
- Базовое ТЗ: `docs/mvp/fishing-forecast-tz.md`.
- Все backend-этапы считаются завершенными только после проверки на `stage` окружении `fazendaserv`.

## Статусы
- `[x]` выполнено
- `[~]` в работе
- `[ ]` не начато

## Этап 0. Foundation (документы и каркас)
- `[x]` Зафиксировано ТЗ MVP.
- `[x]` Поднят базовый FastAPI backend.
- `[x]` Реализованы endpoints `GET /health`, `GET /ready`, `GET /forecast`, `POST /catch`.
- `[x]` Описаны базовые операционные документы (runbook, quality gates, risk register).

## Этап 1. Сервер и деплой на fazendaserv
- `[x]` Подготовлены скрипты:
  - `scripts/deploy-fazendaserv.ps1`
  - `scripts/verify-gate1.ps1`
- `[x]` Зафиксировать сетевой контур для статического IP:
  - зафиксировать внешний endpoint на статическом WAN IP роутера;
  - настроить/проверить NAT (port-forward) на `fazendaserv:8000`;
  - проверить firewall/allowlist правила на роутере и на хосте `fazendaserv`.
- `[x]` Прогнать bootstrap/security baseline на `fazendaserv`:
  - UFW, fail2ban, key-only SSH, security auto-updates.
- `[~]` Проверить автостарт стека после reboot сервера.
- `[x]` Подтвердить Gate 1 на `fazendaserv`:
  - `GET /health` доступен извне;
  - `GET /ready` стабилен;
  - контейнер API в статусе `healthy`.

## Этап 2. Backend data layer (обязательно перед mobile beta)
- `[x]` Добавить в compose сервисы PostgreSQL и Redis.
- `[x]` Вынести конфигурацию подключений в stage/prod env.
- `[x]` Реализовать миграции схемы БД:
  - таблица `catch_records`;
  - индексы по `caught_at`, `species`, `user_id`.
- `[x]` Перевести `POST /catch` с in-memory на PostgreSQL.
- `[x]` Добавить read-through кэш прогноза в Redis.

## Этап 3. Data ingestion + прогнозный слой
- `[x]` Реализовать ingestion прогноза погоды (ежедневный запуск).
- `[x]` Реализовать ingestion температуры воды (fact + forecast).
- `[x]` Включить расчёт фазы луны в daily pipeline.
- `[x]` Добавить freshness/quality checks данных и алерты.
- `[x]` Реализовать режим деградации (`stale=true` + last_update_time).

## Этап 4. ML baseline
- `[x]` Сформировать baseline features для `pike`/`perch`.
- `[x]` Реализовать тренировочный pipeline baseline-модели.
- `[x]` Настроить quality gates (MAE/RMSE/Spearman/Top-day hit-rate).
- `[x]` Реализовать безопасную публикацию модели (canary/smoke).
- `[x]` Подготовить retrain policy по порогам данных.

## Этап 5. API hardening и безопасность
- `[x]` Добавить полноценную auth-схему (замена временного `x-user-id`).
- `[x]` Добавить rate-limit и anti-spam на `POST /catch`.
- `[x]` Добавить аудит-логи по событиям записи улова.
- `[x]` Закрыть внутренние сервисы от внешнего доступа (только нужные порты).
- `[x]` Провести security review конфигурации `fazendaserv`.

## Этап 6. Mobile readiness (зависит от backend)
- `[x]` Зафиксировать стабильный API-контракт `forecast/catch`.
- `[x]` Добавить версионирование API (`/v1`) при необходимости.
- `[x]` Подготовить offline-friendly ответы и коды ошибок.
- `[x]` Документировать mobile integration examples.

## Этап 7. Release readiness
- `[x]` Настроить ежедневный backup БД на `fazendaserv` (ротация 30 дней).
- `[x]` Провести backup/restore drill и зафиксировать RTO/RPO.
- `[x]` Провести rollback rehearsal (backend + модель).
- `[x]` Подготовить legal minimum pack (policy/terms/deletion).
- `[x]` Зафиксировать релизный endpoint API на внешнем статическом IP роутера и проверить доступность извне.
- `[~]` Пройти финальные quality gates (`GO` без P0/P1).

## Ближайший спринт (предлагаемый)
- `[~]` 1) Закрыть Этап 1 на `fazendaserv` (bootstrap + Gate 1 подтверждение).
- `[x]` 2) Добавить PostgreSQL/Redis в compose.
- `[x]` 3) Перенести `POST /catch` на PostgreSQL.
- `[x]` 4) Подготовить smoke-набор API для stage.

## Правило приоритизации
- P0: доступность и целостность данных на `fazendaserv`.
- P1: стабильность API-контракта для mobile.
- P2: улучшения качества модели и UX.
- Любая новая фича вне ТЗ MVP — только после закрытия P0/P1 блока.
