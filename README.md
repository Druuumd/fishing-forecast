# Fishing Forecast MVP

Базовый инфраструктурный каркас для Фазы 1:
- backend API на FastAPI;
- Docker Compose для stage/prod c `api + postgres + redis`;
- health/readiness endpoint (readiness проверяет доступность БД и Redis);
- structured JSON logs с `trace_id`.

## Основная целевая среда
Проект разворачивается на сервере `fazendaserv (192.168.0.250)`.

## Деплой на fazendaserv (stage)
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-fazendaserv.ps1
```

Во время деплоя автоматически выполняются миграции БД (`alembic upgrade head`) внутри контейнера `api`.

Проверка:
```bash
curl http://192.168.0.250:8000/health
curl http://192.168.0.250:8000/ready
```

Остановка на сервере:
```bash
ssh drumd@192.168.0.250 "cd /home/drumd/fishing-forecast && docker compose -f docker-compose.yml -f docker-compose.stage.yml down"
```

Проверка Gate 1:
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\verify-gate1.ps1
```

Smoke-проверка API (stage):
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-stage.ps1
```

Проверка сетевого hardening (должен быть открыт только API порт):
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\verify-network-hardening.ps1
```

Backup/Restore (fazendaserv):
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\backup-db-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\restore-drill-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\install-backup-cron-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\rollback-rehearsal-fazendaserv.ps1
```

Host bootstrap/security checks (fazendaserv):
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\verify-bootstrap-security-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify-autostart-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\harden-host-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\prepare-root-hardening-fazendaserv.ps1
```

Final quality gates (fazendaserv + WAN):
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\run-final-quality-gates-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-final-quality-gates-fazendaserv.ps1 -EnableDomainChecks
powershell -ExecutionPolicy Bypass -File .\scripts\verify-legal-readiness-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\set-legal-config-fazendaserv.ps1 -ContactEmail "<email>" -SupportEmail "<email>" -PrivacyUrl "<url>" -TermsUrl "<url>" -DataDeletionUrl "<url>" -CookieTrackingUrl "<url>"
```

Weather ingestion / DQ (fazendaserv):
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\run-weather-ingest-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-weather-dq-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-ml-retrain-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-ml-latest-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-ml-active-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-ml-publish-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-export-me-data-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-delete-me-data-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-mobile-beta-pass-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\install-weather-ingest-cron-fazendaserv.ps1
```

Mobile UX beta client:
```bash
cd .\mobile-web
python -m http.server 4173
```

Full Web app (React + Vite):
```bash
cd .\web
npm install
npm run dev
```

Domain/TLS setup (kvh-forecast.ru + api.kvh-forecast.ru):
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\setup-domain-tls-fazendaserv.ps1 -Email "admin@kvh-forecast.ru"
powershell -ExecutionPolicy Bypass -File .\scripts\renew-domain-tls-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-web-domain.ps1
```
Примечание:
- На `fazendaserv` `:80/:443` обслуживаются контейнером `caddy`; скрипт настраивает доменные роуты через него.
- Для успешного публичного smoke DNS записи должны указывать на WAN IP `84.22.146.195`:
  - `A kvh-forecast.ru -> 84.22.146.195`
  - `A api.kvh-forecast.ru -> 84.22.146.195`

Android app (native shell):
```bash
# Open in Android Studio:
.\android
```
См. `android/README.md`.

## Локальный запуск (только для отладки)
```bash
docker compose -f docker-compose.yml -f docker-compose.stage.yml up --build -d
```

Применить миграции локально:
```bash
docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T api alembic upgrade head
```

## Запуск в prod-конфигурации
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

## Текущее API
- `GET /v1/health` - liveness.
- `GET /v1/ready` - readiness.
- `POST /v1/auth/login` - получение bearer-токена для API.
- `GET /v1/forecast` - 7-дневный прогноз по видам `pike`/`perch`.
- `POST /v1/catch` - отправка записи улова с привязкой к ближайшему погодному снимку (требует `Authorization: Bearer <token>`).
- `POST /v1/admin/ingest/weather` - ручной запуск ingest прогноза погоды (bearer required).
- `GET /v1/admin/dq/weather` - проверка качества weather snapshots (bearer required).
- `POST /v1/admin/ml/retrain` - обучение baseline-калибровки по фактическим уловам (bearer required).
- `GET /v1/admin/ml/latest` - получение последней версии baseline-модели и метрик (bearer required).
- `GET /v1/admin/ml/active` - получение активной (опубликованной) модели для прод-прогноза.
- `POST /v1/admin/ml/publish` - безопасная публикация candidate-модели после smoke-проверок.
- `PUT /v1/consent` - запись согласий пользователя (`geo/push/analytics`) (bearer required).
- `GET /v1/consent/me` - чтение текущих согласий пользователя (bearer required).
- `GET /v1/me/data` - экспорт пользовательских данных (DSAR access).
- `DELETE /v1/me/data` - удаление пользовательских данных (уловы + consent) по запросу пользователя.
- `GET /v1/legal/info` - публичная legal-метаинформация (контакты и URL policy/terms/deletion/cookie).

Примечание:
- `GET /forecast` использует read-through кэш в Redis (`FORECAST_CACHE_TTL_SEC`).
- `POST /catch` защищен от злоупотреблений:
  - rate-limit (`CATCH_RATE_LIMIT_WINDOW_SEC`, `CATCH_RATE_LIMIT_MAX_REQUESTS`);
  - anti-spam дубликатов (`CATCH_DUPLICATE_WINDOW_SEC`).
- Для `POST /catch` пишется аудит-событие в structured logs (`catch_submission_audit`) с outcome: `accepted`/`rejected`.
- Ошибки API возвращаются в едином формате `error.code/error.retryable/error.request_id` (удобно для offline-очереди mobile).
- Ответ `/v1/forecast` включает `last_updated_at`; при устаревших/отсутствующих данных флаг `days[].stale=true`.
- Weather ingest использует `Open-Meteo weather + marine` с `past_days + forecast_days` (fact + forecast); при недоступности marine-данных включается proxy fallback для `water_temp_c`.
- `POST /v1/catch` при привязке погодного снимка сначала использует historical weather snapshots из БД (если доступны), затем fallback на встроенный синтетический профиль.
- В `/v1/forecast` применяется только `active` ML-модель; `retrain` создает `candidate` и не влияет на прод до `publish`.
- Серверный контур consent для legal/mobile готов: хранение `geo/push/analytics` в `user_consents`.

### Примеры запросов
```bash
curl -X POST "http://192.168.0.250:8000/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo123"}'
```

```bash
curl "http://192.168.0.250:8000/v1/forecast?species=pike"
```

```bash
curl -X POST "http://192.168.0.250:8000/v1/catch" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"species":"perch","score":4.2,"latitude":55.99,"longitude":92.88,"note":"утренний выход"}'
```

```bash
curl -X POST "http://192.168.0.250:8000/v1/admin/ingest/weather" \
  -H "Authorization: Bearer <access_token>"
```

Примечание:
- legacy-маршруты без префикса (`/health`, `/ready`, `/auth/login`, `/forecast`, `/catch`) сохранены как совместимые алиасы.

## Логирование
- Формат: JSON в stdout.
- Поля: `timestamp`, `level`, `logger`, `message`, `trace_id`, `method`, `path`, `status_code`, `elapsed_ms`.

## Security review
- Отчет по текущей проверке хоста: `docs/ops/security-review-fazendaserv-2026-04-20.md`.
- Отчет по backup/restore drill: `docs/ops/backup-restore-drill-2026-04-20.md`.
- Отчет по rollback rehearsal: `docs/ops/rollback-rehearsal-2026-04-20.md`.
- Журнал выполненных работ: `docs/ops/WORK_JOURNAL.md`.
- Gate-статус релиза: `docs/mvp/release-gate-status-2026-04-21.md`.
- Release command center: `docs/mvp/release-command-center-2026-04-21.md`.
- Release GO memo: `docs/mvp/release-go-memo-2026-04-21.md`.

## Mobile integration
- Примеры интеграции и обработка offline/error flow: `docs/mvp/mobile-integration-examples.md`.
- Handoff-пакет для mobile команды: `docs/mvp/mobile-handoff-pack-2026-04-21.md`.
- Бета-чеклист тестов mobile: `docs/mvp/mobile-beta-test-cases-2026-04-21.md`.
- Android приложение: `android/README.md`.
- Android release checklist: `docs/mvp/android-release-checklist-2026-04-21.md`.
- Web приложение: `web/README.md`.

## Следующий шаг
Развернуть web-контур на `kvh-forecast.ru` / `api.kvh-forecast.ru`, выпустить TLS и пройти domain smoke.
