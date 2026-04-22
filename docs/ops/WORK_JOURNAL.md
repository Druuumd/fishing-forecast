# Журнал выполненных работ

## Правило ведения
- Этот журнал обновляется после каждого значимого изменения в backend, деплое, безопасности или операционных процедурах.
- Формат записи: дата, блок работ, что сделано, результат проверки.

## 2026-04-20

### 1) MVP backend и API
- Реализован backend на FastAPI с endpoint:
  - `GET /health`, `GET /ready`
  - `GET /forecast` / `GET /v1/forecast`
  - `POST /catch` / `POST /v1/catch`
  - `POST /auth/login` / `POST /v1/auth/login`
- Включены legacy-алиасы без `/v1` для обратной совместимости.
- Проверка: smoke и gate1 проходят на `fazendaserv`.

### 2) Данные и хранилище
- Подключены PostgreSQL и Redis в `docker-compose`.
- `POST /catch` переведен с in-memory на PostgreSQL.
- Добавлены миграции Alembic:
  - initial migration `20260420_0001` (`catch_records` + индексы).
- Включен read-through cache прогноза в Redis.
- Проверка: readiness показывает `db=up`, `redis=up`; запись улова в БД подтверждена.

### 3) Безопасность API
- Добавлена auth-схема на bearer JWT.
- Включены rate-limit и anti-spam duplicate check для `POST /catch`.
- Добавлены аудит-логи `catch_submission_audit` с outcome/reason.
- Введен единый offline-friendly формат ошибок:
  - `error.code`, `error.message`, `error.retryable`, `error.request_id`, `error.details`.
- Проверка: подтверждены ответы `401`, `409`, `429` и успешный `201`.

### 4) Сетевой hardening
- Изоляция сетей compose:
  - `backend` internal-only для `db/redis`;
  - внешний доступ только к `api:8000`.
- Добавлен скрипт `scripts/verify-network-hardening.ps1`.
- Проверка: `8000` открыт, `5432/6379` закрыты.

### 5) Операционные процедуры
- Реализованы и проверены:
  - `scripts/backup-db-fazendaserv.ps1`
  - `scripts/restore-drill-fazendaserv.ps1`
  - `scripts/install-backup-cron-fazendaserv.ps1`
  - `scripts/rollback-rehearsal-fazendaserv.ps1`
- Настроен daily backup cron на `03:00`, retention 30 дней.
- Зафиксированы отчеты:
  - `docs/ops/security-review-fazendaserv-2026-04-20.md`
  - `docs/ops/backup-restore-drill-2026-04-20.md`
  - `docs/ops/rollback-rehearsal-2026-04-20.md`

## Последнее обновление
- 2026-04-20 (создание журнала и ретроспективное заполнение).

## 2026-04-21

### 6) Сверка с исходным планом
- Выполнена формальная сверка "план vs факт":
  - источник плана: `docs/mvp/final-plan.md`, `FISHING_FORECAST_MVP_SCOPE_FREEZE.md`;
  - источник факта: `docs/mvp/ROADMAP.md`, текущая реализация и ops-артефакты.
- Добавлен отчет: `docs/mvp/plan-reconciliation-2026-04-20.md`.
- Зафиксированы закрытые/частично закрытые/незакрытые блоки и остаток до MVP.

### 7) Data ingestion и деградация прогноза
- Добавлена БД-модель и миграция `weather_snapshots` (`20260421_0002`).
- Реализован сервис ingestion Open-Meteo:
  - ручной запуск через `POST /v1/admin/ingest/weather`;
  - утилита запуска `scripts/run-weather-ingest-fazendaserv.ps1`.
- `GET /v1/forecast` теперь:
  - использует загруженные weather snapshots при свежих данных;
  - возвращает `last_updated_at`;
  - переходит в деградационный режим (`stale=true`) при устаревании/отсутствии свежих данных.
- Проверка:
  - деплой и миграция на `fazendaserv` успешны;
  - ingest вернул `rows=7`;
  - `/v1/forecast` возвращает `last_updated_at` и `stale=false` после ingest.

### 8) DQ checks + legal pack + gate-фиксация
- Добавлен weather DQ контур:
  - endpoint: `GET /v1/admin/dq/weather`;
  - утилита: `scripts/run-weather-dq-fazendaserv.ps1`;
  - cron-инсталлятор ingest+DQ: `scripts/install-weather-ingest-cron-fazendaserv.ps1`.
- Добавлены legal документы MVP:
  - `docs/legal/privacy-policy-mvp.md`
  - `docs/legal/terms-of-use-mvp.md`
  - `docs/legal/data-deletion-policy-mvp.md`
  - обновлен `docs/legal/release-legal-checklist.md`.
- Добавлен gate-отчет:
  - `docs/mvp/release-gate-status-2026-04-21.md`.
- Проверка:
  - DQ endpoint возвращает `status=ok`;
  - ingest и DQ ручной прогон на `fazendaserv` успешны;
  - cron-записи backup/ingest/DQ установлены.

### 9) ML baseline pipeline + retrain policy
- Добавлен ML-контур baseline-калибровки:
  - миграция `20260421_0003` с таблицей `ml_model_versions`;
  - хранение версии модели (bias по видам + метрики) в БД.
- Реализован retrain pipeline:
  - endpoint `POST /v1/admin/ml/retrain`;
  - endpoint `GET /v1/admin/ml/latest`;
  - порог retrain через `ML_RETRAIN_MIN_RECORDS`.
- В прогноз добавлена модельная калибровка:
  - `GET /v1/forecast` применяет latest model `species_bias` при наличии;
  - после retrain очищается Redis cache прогноза.
- Добавлены метрики baseline quality gates:
  - `MAE`, `RMSE`, `Spearman`, `Top-day hit-rate` по `pike/perch`.
- Добавлены утилиты:
  - `scripts/run-ml-retrain-fazendaserv.ps1`
  - `scripts/run-ml-latest-fazendaserv.ps1`
  - обновлен `scripts/install-weather-ingest-cron-fazendaserv.ps1` (добавлен cron retrain 03:25).

### 10) Safe publish (canary/smoke) для ML
- Добавлен безопасный контур публикации модели:
  - retrain создает `candidate` и сохраняет smoke-результаты;
  - в `forecast` используется только `active` модель;
  - активация выполняется вручную через publish endpoint.
- Добавлены endpoints:
  - `GET /v1/admin/ml/active`
  - `POST /v1/admin/ml/publish` (`model_id` optional).
- Добавлены smoke thresholds в конфиг:
  - `ML_SMOKE_MAX_MAE`
  - `ML_SMOKE_MAX_RMSE`
  - `ML_SMOKE_MIN_TOP_DAY_HIT_RATE`.
- Добавлены утилиты:
  - `scripts/run-ml-active-fazendaserv.ps1`
  - `scripts/run-ml-publish-fazendaserv.ps1`.

### 11) Улучшение ingestion температуры воды
- В `weather_ingest` добавлен источник marine API Open-Meteo для `sea_surface_temperature` (daily).
- Включен fallback на proxy-расчет только если marine-данные недоступны по дню/локации.
- В `source` ingestion фиксируется происхождение данных:
  - `open-meteo+marine` или `open-meteo+proxy`.

### 12) Bootstrap/security baseline + autostart checks (без WAN)
- Добавлены operational scripts:
  - `scripts/verify-bootstrap-security-fazendaserv.ps1`
  - `scripts/verify-autostart-fazendaserv.ps1`
  - `scripts/harden-host-fazendaserv.ps1`
- Зафиксированы результаты проверки хоста:
  - autostart readiness: `PASS` (docker enabled + restart policy + local ready=200);
  - security baseline: `PARTIAL` (обнаружен `PasswordAuthentication yes` в sshd_config).
- Подготовлен отдельный отчет:
  - `docs/ops/bootstrap-security-check-2026-04-21.md`.

### 13) WAN endpoint подтвержден (Archer AX55)
- На TP-Link Archer AX55 настроен port-forward:
  - `TCP/8000 -> 192.168.0.250:8000`.
- Подтверждена внешняя доступность API:
  - `84.22.146.195:8000/health` -> `{"status":"ok"}`;
  - `84.22.146.195:8000/ready` -> `{"status":"ready","env":"stage","db":"up","redis":"up"}`.
- Добавлен отчет:
  - `docs/ops/wan-endpoint-validation-2026-04-21.md`.

### 14) Финальные technical quality gates
- Добавлен единый сценарий прогона:
  - `scripts/run-final-quality-gates-fazendaserv.ps1`.
- Прогнаны проверки:
  - Gate1 (LAN), smoke, network hardening, weather DQ, active ML, WAN `/health` и `/ready`.
- Итог прогона: `PASS`.
- Добавлен отчет:
  - `docs/mvp/final-quality-gates-2026-04-21.md`.

### 15) Fact+forecast ingestion + привязка уловов к historical snapshots
- `weather_ingest` обновлен до `past_days + forecast_days` для weather и marine источников.
- Расчет `air_temp_c` переведен на `temperature_2m_mean` (с fallback к max/min).
- `POST /v1/catch` теперь при линковке погоды использует historical snapshots из БД (если есть), а не только синтетический профиль.
- Статус пункта roadmap "ingestion температуры воды (fact + forecast)" переведен в выполненный.
- Проверка на `fazendaserv`:
  - deploy + smoke: успешно;
  - weather ingest: успешно;
  - weather DQ: `status=ok`;
  - final technical gates: `PASS`.

### 16) Consent API для legal/mobile
- Добавлен backend-контур согласий пользователя:
  - миграция `20260421_0005` (`user_consents`);
  - endpoint `PUT /v1/consent` (upsert consent);
  - endpoint `GET /v1/consent/me` (чтение текущего состояния).
- Обновлены документы:
  - `README.md` (новые endpoints);
  - `docs/mvp/mobile-integration-examples.md` (примеры consent API);
  - `docs/legal/release-legal-checklist.md` (consent пункты переведены в partial на уровне backend).
- Проверка на `fazendaserv`:
  - deploy + миграция `20260421_0005`: успешно;
  - `PUT /v1/consent` и `GET /v1/consent/me`: успешно;
  - `smoke-stage.ps1` обновлен и проходит с consent flow;
  - final technical gates: `PASS`.

### 17) DSAR self-service delete API
- Добавлен endpoint:
  - `DELETE /v1/me/data` (удаление пользовательских уловов и consent-профиля).
- Добавлен operational script:
  - `scripts/run-delete-me-data-fazendaserv.ps1`.
- Обновлен consolidated gate-script:
  - `scripts/run-final-quality-gates-fazendaserv.ps1` (добавлен шаг `dsar_delete_me_data`).
- Обновлены legal/mobile документы:
  - `docs/legal/data-deletion-policy-mvp.md`
  - `docs/legal/release-legal-checklist.md`
  - `docs/mvp/mobile-integration-examples.md`
  - `README.md`.
- Проверка на `fazendaserv`:
  - DSAR delete flow: успешно;
  - final technical gates (включая DSAR): `PASS`.

### 18) DSAR self-service export API + legal data governance docs
- Добавлен endpoint:
  - `GET /v1/me/data` (экспорт пользовательских данных: уловы + consent).
- Добавлен operational script:
  - `scripts/run-export-me-data-fazendaserv.ps1`.
- Обновлен consolidated gate-script:
  - `scripts/run-final-quality-gates-fazendaserv.ps1` (добавлен шаг `dsar_export_me_data`).
- Добавлены legal docs:
  - `docs/legal/cookie-tracking-notice-mvp.md`
  - `docs/legal/data-inventory-mvp.md`
- Обновлены документы:
  - `docs/legal/release-legal-checklist.md`
  - `docs/legal/data-deletion-policy-mvp.md`
  - `docs/mvp/mobile-integration-examples.md`
  - `README.md`.
- Проверка на `fazendaserv`:
  - DSAR export flow: успешно;
  - final technical gates (включая DSAR export/delete): `PASS`.

### 19) Release command center + root-hardening one-command path
- Добавлены скрипты для закрытия host security остатка:
  - `scripts/fazendaserv-root-hardening.sh`
  - `scripts/prepare-root-hardening-fazendaserv.ps1`
- Добавлен единый релизный command center:
  - `docs/mvp/release-command-center-2026-04-21.md`
  - содержит последовательность шагов и критерии GO/NO-GO.
- Обновлены ссылки в:
  - `README.md`
  - `docs/ops/bootstrap-security-check-2026-04-21.md`
  - `docs/mvp/release-gate-status-2026-04-21.md`.

### 20) Закрытие host security остатка (SSH password auth off)
- Root hardening применен на `fazendaserv` в интерактивной sudo-сессии:
  - `PasswordAuthentication no`
  - `PubkeyAuthentication yes`
  - `PermitRootLogin no`
  - `ufw/fail2ban/unattended-upgrades`: active+enabled.
- Проверка:
  - `scripts/verify-bootstrap-security-fazendaserv.ps1` -> `status=ok`.
  - `scripts/verify-autostart-fazendaserv.ps1` -> `status=ok`.
  - `scripts/run-final-quality-gates-fazendaserv.ps1` -> `overall=PASS`.
- Улучшение tooling:
  - `scripts/prepare-root-hardening-fazendaserv.ps1` теперь автоматически нормализует CRLF на сервере перед запуском (`sed -i 's/\r$//'`).

### 21) Legal contacts/public URLs backend finalization tooling
- Добавлен публичный backend endpoint:
  - `GET /v1/legal/info` (контакты + ссылки policy/terms/deletion/cookie из env).
- Добавлен инструмент валидации legal readiness:
  - `scripts/verify-legal-readiness-fazendaserv.ps1`.
- Добавлен инструмент применения production legal-конфига на `fazendaserv`:
  - `scripts/set-legal-config-fazendaserv.ps1`.
- Добавлены legal data-governance документы:
  - `docs/legal/cookie-tracking-notice-mvp.md`
  - `docs/legal/data-inventory-mvp.md`.
- Проверка на `fazendaserv`:
  - endpoint `/v1/legal/info` доступен;
  - legal readiness сейчас `degraded` из-за placeholder значений (ожидаемо до подстановки реальных контактов/URL).

### 22) Привязка legal контактов/URL к домену `kvh-forecast.ru`
- Для stage/prod env и backend defaults установлены значения:
  - `privacy@kvh-forecast.ru`, `legal@kvh-forecast.ru`
  - `https://kvh-forecast.ru/privacy`
  - `https://kvh-forecast.ru/terms`
  - `https://kvh-forecast.ru/data-deletion`
  - `https://kvh-forecast.ru/cookie-tracking`
- Проверка на `fazendaserv`:
  - `GET /v1/legal/info` возвращает значения `kvh-forecast.ru`;
  - `scripts/verify-legal-readiness-fazendaserv.ps1` -> `status=ok`.

### 23) Mobile handoff pack + beta test checklist
- Подготовлен релизный handoff-пакет для mobile:
  - `docs/mvp/mobile-handoff-pack-2026-04-21.md`.
- Подготовлен beta-чеклист тестирования mobile flow:
  - `docs/mvp/mobile-beta-test-cases-2026-04-21.md`.
- Обновлены ссылки и release-артефакты:
  - `docs/mvp/release-command-center-2026-04-21.md`
  - `docs/mvp/release-gate-status-2026-04-21.md`
  - `README.md`.

### 24) Release GO memo (one-page decision artifact)
- Добавлен финальный decision-документ:
  - `docs/mvp/release-go-memo-2026-04-21.md`
- В memo зафиксированы:
  - текущий вердикт `CONDITIONAL NO-GO`;
  - закрытые backend/infra/security/legal-config блоки;
  - остатки до полного GO (mobile UX + beta PASS);
  - критерии финального sign-off.
- Обновлены ссылки:
  - `docs/mvp/release-command-center-2026-04-21.md`
  - `docs/mvp/release-gate-status-2026-04-21.md`
  - `README.md`.

### 25) Mobile UX implementation baseline + beta PASS automation
- Реализован mobile-friendly UX клиент:
  - `mobile-web/index.html`
  - `mobile-web/app.js`
  - `mobile-web/styles.css`
  - `mobile-web/README.md`
- Покрытые UX flow:
  - login / forecast / catch + offline queue;
  - consent read/update;
  - DSAR export/delete;
  - legal links из `GET /v1/legal/info`.
- Добавлен автоматизированный beta-pass скрипт:
  - `scripts/run-mobile-beta-pass-fazendaserv.ps1`.
- Проверка:
  - `run-mobile-beta-pass-fazendaserv.ps1` -> `overall=PASS` (TC-01..TC-07).
  - `run-final-quality-gates-fazendaserv.ps1` -> `overall=PASS`.

### 26) Full mobile UX polish + расширенный beta PASS (TC-01..TC-09)
- Расширен mobile web клиент до full MVP UX уровня:
  - карта и геолокация (`Map + Geo`) с автозаполнением координат в catch-форме;
  - push flow для web beta (`Enable Notifications`, `Test Notification`);
  - добавлен PWA-контур (`manifest.webmanifest`, `sw.js`) для offline cache shell.
- Обновлен beta-pass automation:
  - `scripts/run-mobile-beta-pass-fazendaserv.ps1` дополнен кейсами:
    - `TC-08` offline queue replay simulation;
    - `TC-09` auth expiry handling (`invalid token -> 401 -> relogin -> retry`).
- Обновлены release-артефакты:
  - `docs/mvp/mobile-beta-test-cases-2026-04-21.md`
  - `docs/mvp/release-gate-status-2026-04-21.md`
  - `docs/mvp/release-command-center-2026-04-21.md`
  - `docs/mvp/release-go-memo-2026-04-21.md`
  - `README.md`.
- Проверка:
  - `run-mobile-beta-pass-fazendaserv.ps1` -> `overall=PASS`, `TC-01..TC-09` все `PASS`.

### 27) Android native app (APK target) поверх mobile MVP
- Создан полноценный Android-проект `android/` (Kotlin + Android Gradle):
  - пакет: `ru.kvh.forecast`;
  - launcher activity: `MainActivity`;
  - минимальный UI-контейнер через `WebView`.
- Мобильный UX из `mobile-web` подключен как assets source для Android сборки:
  - `android/app/build.gradle.kts` -> `assets.srcDirs("../../mobile-web")`.
- Добавлены Android runtime permissions и platform-интеграция:
  - INTERNET/network state, location (geo), notifications (Android 13+);
  - cleartext traffic для stage/WAN (`http://...:8000`);
  - native bridge `AndroidBridge` для test push notification.
- Добавлена Android документация:
  - `android/README.md` (запуск, сборка APK, связь с mobile-web assets).
- Обновлены:
  - `.gitignore` (android build artifacts),
  - `README.md` (android секция и следующий шаг по signed APK/AAB).

### 28) Android production prep (release-ready baseline)
- Подготовлен Android release baseline:
  - adaptive launcher icon;
  - splash theme `Theme.KvhForecast.Starting`;
  - network security config (`res/xml/network_security_config.xml`);
  - release build optimization (`minifyEnabled`, `shrinkResources`).
- Добавлен release signing контур:
  - `android/app/build.gradle.kts` читает `android/keystore.properties` (если присутствует);
  - добавлен шаблон `android/keystore.properties.example`;
  - `android/keystore.properties` и `android/keystore/` добавлены в `.gitignore`.
- Добавлен versioning через Gradle properties:
  - `APP_VERSION_CODE`, `APP_VERSION_NAME`.
- Добавлена документация:
  - `docs/mvp/android-release-checklist-2026-04-21.md`;
  - обновлен `android/README.md` (signed APK/AAB flow);
  - обновлены `README.md` и `docs/mvp/release-command-center-2026-04-21.md`.

### 29) Full web application baseline (React + Vite)
- Создан новый frontend модуль `web/`:
  - `web/package.json`, `web/vite.config.js`, `web/index.html`;
  - `web/src/main.jsx`, `web/src/App.jsx`, `web/src/styles.css`;
  - `web/.env.example`, `web/README.md`.
- Перенесены и адаптированы MVP сценарии из mobile UX:
  - auth/login, forecast, catch + offline queue;
  - consent update/read, DSAR export/delete, legal links;
  - map + geolocation.
- Введена конфигурация API base URL через `VITE_API_BASE_URL` (без hardcode WAN IP в коде web app).
- Проверка:
  - `cd web && npm install && npm run build` -> `PASS` (`web/dist` сформирован).

### 30) Domain web infra (Nginx + TLS path) и deploy automation
- Добавлен web/reverse-proxy контур:
  - `docker-compose.web.yml` (nginx + certbot);
  - `docker-compose.web-ssl.yml` (SSL-конфиг nginx).
- Добавлены nginx конфиги:
  - `infra/nginx/conf.d/kvh-http.conf` (HTTP + ACME webroot + static/proxy);
  - `infra/nginx/conf.d/kvh-ssl.conf` (HTTPS frontend + API proxy).
- Добавлены TLS automation scripts:
  - `scripts/setup-domain-tls-fazendaserv.ps1` (issue cert + switch to SSL);
  - `scripts/renew-domain-tls-fazendaserv.ps1` (renew + nginx restart).
- Обновлен deploy:
  - `scripts/deploy-fazendaserv.ps1` теперь собирает `web`, копирует `web/dist`, `infra`, `docker-compose.web*.yml` и поднимает nginx контур.
- Добавлен domain smoke:
  - `scripts/smoke-web-domain.ps1`.

### 31) QA/regression + release docs update для web publish
- Проверки:
  - `scripts/smoke-stage.ps1` -> `PASS`.
  - `scripts/run-mobile-beta-pass-fazendaserv.ps1` -> `PASS` (TC-01..TC-09).
  - `scripts/smoke-web-domain.ps1` -> `FAIL` (TLS handshake до фактического выпуска сертификатов).
- Обновлены документы:
  - `README.md` (web run + domain TLS scripts + domain gates);
  - `docs/mvp/release-command-center-2026-04-21.md`;
  - `docs/mvp/release-gate-status-2026-04-21.md`;
  - `docs/mvp/release-go-memo-2026-04-21.md`.

### 32) End-to-end server rollout web+domain (операционный прогон)
- Выполнен фактический деплой на `fazendaserv`:
  - `scripts/deploy-fazendaserv.ps1` (web build + remote compose up + migrations).
- Обнаружен конфликт порта `80` (занят существующим `caddy`) и исправлен контур:
  - frontend `nginx` переведен на `8081`;
  - доменный reverse proxy и TLS оставлены на `caddy` (`80/443`).
- Добавлен caddy patch workflow:
  - `infra/caddy/kvh-domain-block.caddy`;
  - `scripts/fazendaserv-patch-caddy.sh`;
  - `scripts/setup-domain-tls-fazendaserv.ps1` обновлен на CRLF-safe flow через `scp + remote .sh`.
- Исправлен runtime issue frontend:
  - `Permission denied` на `web/dist/index.html` внутри nginx;
  - добавлен `chmod -R a+rX` после доставки `dist` в deploy-скрипт.
- Проверка текущего состояния:
  - backend gates: `PASS` (`run-final-quality-gates-fazendaserv.ps1`);
  - forced domain routing test (`curl --resolve ... 84.22.146.195`):
    - `https://kvh-forecast.ru` -> `200`;
    - `https://api.kvh-forecast.ru/v1/ready` -> `200`.
- Финальный внешний блокер:
  - DNS записи домена пока не указывают на `84.22.146.195`:
    - `kvh-forecast.ru` резолвится на другой IP;
    - `api.kvh-forecast.ru` отсутствует (NXDOMAIN);
  - из-за этого `scripts/smoke-web-domain.ps1` по публичным доменам пока `FAIL`.

### 33) Hotfix `Failed to fetch` в web login
- Причина:
  - web-клиент ходил на отдельный API base URL, что давало сетевой сбой при несогласованном DNS/доменном контуре.
- Исправления:
  - `web/src/App.jsx`: добавлен устойчивый `inferApiDefault()` (предпочтение same-origin на `kvh-forecast.ru`);
  - `web/src/App.jsx`: улучшен `NETWORK_ERROR` payload с диагностикой URL;
  - `infra/nginx/conf.d/kvh-http.conf` и `infra/nginx/conf.d/kvh-ssl.conf`:
    - добавлен proxy для `/v1/*`, `/health`, `/ready` на backend `api:8000`.
- Операционно:
  - выполнен redeploy и перезапуск `fishing-forecast-nginx-1` для применения конфигов;
  - проверено forced-domain тестом (`--resolve`):
    - `GET https://kvh-forecast.ru/v1/ready` -> `200`.

### 34) Обновление формулы прогноза: сезон + скорость/направление ветра
- Расширен погодный профиль в backend:
  - в `WeatherSnapshot` добавлены `wind_speed_m_s`, `wind_direction_deg`;
  - эти поля теперь хранятся в `weather_snapshots` и линкованных `catch_records`.
- Добавлена миграция БД:
  - `backend/alembic/versions/20260422_0006_add_wind_inputs_to_forecast.py`.
- Обновлен ingest Open-Meteo:
  - запрашиваются `wind_speed_10m_max` (в `m/s`) и `wind_direction_10m_dominant`;
  - данные ветра записываются в weather snapshots.
- Обновлена формула скоринга:
  - добавлены `wind_speed_factor` и `wind_direction_factor`;
  - добавлен явный `season_factor` по виду рыбы (`pike`, `perch`).
- Обновлены API модели:
  - `ForecastDay` теперь возвращает `wind_speed_m_s` и `wind_direction_deg`.
- Проверка:
  - deploy на `fazendaserv` + миграция `20260422_0006`: успешно;
  - weather ingest: успешно;
  - `GET /v1/forecast?species=pike` возвращает wind-поля и актуальные значения.
