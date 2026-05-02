# KVH Forecast — Operations Runbook

*Обновлено: 2026-04-27*

Practical reference: how to do common operational tasks. Каждая секция —
независимая, копируй-вставляй команды.

> **Хост**: `fazendaserv` через Tailscale `100.106.177.127` или
> локальный LAN `192.168.0.250`. Пользователь: `drumd`.
> Корень репозитория на сервере: `~/fishing-forecast/`.

---

## Quick reference

| Задача | Команда |
|--------|---------|
| Ручной ingest | `bash ~/fishing-forecast/scripts/kvh-cron-daily.sh` |
| Проверить health | `curl -sk https://kvh-forecast.ru/v1/ready` |
| Перезапустить API | `cd ~/fishing-forecast && docker compose -f docker-compose.yml -f docker-compose.stage.yml restart api` |
| Прогнать тесты | `docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T api pytest tests/ -q` |
| Применить миграции | `docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T api alembic upgrade head` |
| Тейл лога cron | `tail -f ~/fishing-forecast/logs/kvh-daily-$(date +%Y-%m-%d).log` |

---

## 1. Daily ingest и cron

### 1.1 Ручной trigger

```bash
ssh drumd@100.106.177.127 'bash ~/fishing-forecast/scripts/kvh-cron-daily.sh'
```

Скрипт:
1. Логин в `/v1/auth/login` (demo/demo123)
2. POST `/v1/admin/ingest/weather` (per-zone Open-Meteo + temperaturavody +
   water-level scrape best-effort + push dispatch)
3. GET `/v1/admin/dq/weather` (data-quality)
4. POST `/v1/admin/ml/retrain` (best-effort)

Лог: `~/fishing-forecast/logs/kvh-daily-YYYY-MM-DD.log`. Старые
автоматически удаляются через `LOG_RETENTION_DAYS=14`.

### 1.2 Проверить что ночной cron отработал

```bash
ssh drumd@100.106.177.127 'tail -20 ~/fishing-forecast/logs/kvh-daily-$(date +%Y-%m-%d).log'
```

Хороший прогон выглядит так:
```
[ts] === daily run started ===
[ts] login ok (token len=145)
[ts] ingest: {"status":"ok","rows":126,"zones":{...},"water_level":{"status":"no_source"...},"push":{"sent":0,...}}
[ts] dq: {"status":"ok","checks":{"freshness":{"ok":true...}}}
[ts] ml_retrain: {"status":"skipped","reason":"not enough records: 16 < 20"}
[ts] === daily run completed ===
```

Если `login ok` нет — проверь `auth_demo_user`/`auth_demo_password` в
`.env.stage.example`.

### 1.3 Crontab

```bash
ssh drumd@100.106.177.127 'crontab -l'
```

Должна быть строка:
```
10 3 * * * /home/drumd/fishing-forecast/scripts/kvh-cron-daily.sh
```

03:10 = 03:10 KRSK = 20:10 UTC прошедшего дня.

Если строки нет:
```bash
ssh drumd@100.106.177.127 '(crontab -l 2>/dev/null; echo "10 3 * * * /home/drumd/fishing-forecast/scripts/kvh-cron-daily.sh") | crontab -'
```

---

## 2. Уровень воды

### 2.1 Внести замер

```bash
TOKEN=$(ssh drumd@100.106.177.127 'curl -sk -X POST https://kvh-forecast.ru/v1/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"demo\",\"password\":\"demo123\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)[\"access_token\"])"')

ssh drumd@100.106.177.127 "curl -sk -X POST https://kvh-forecast.ru/v1/admin/water-level \
  -H 'Authorization: Bearer $TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{\"day\":\"2026-04-27\",\"level_m\":228.5,\"source\":\"manual\",\"note\":\"daily check\"}'"
```

После upsert forecast cache очищается автоматически — следующий
GET `/v1/forecast` подхватит новый уровень.

### 2.2 Backfill за период

Скрипт `scripts/backfill_water_levels.sh` (создать при необходимости):

```bash
#!/usr/bin/env bash
TOKEN=$(curl -fsS -X POST http://127.0.0.1:8000/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"demo123"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

while IFS=, read -r day level; do
  curl -fsS -X POST http://127.0.0.1:8000/v1/admin/water-level \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"day\":\"$day\",\"level_m\":$level,\"source\":\"backfill\"}"
done < levels.csv
```

Формат `levels.csv`: `2026-04-01,230.45`.

### 2.3 Текущее состояние

```bash
ssh drumd@100.106.177.127 'curl -sk https://kvh-forecast.ru/v1/water-level/history?days=7 | python3 -m json.tool'
```

Или для админки:
```bash
ssh drumd@100.106.177.127 "curl -sk -H 'Authorization: Bearer $TOKEN' \
  https://kvh-forecast.ru/v1/admin/water-level/latest | python3 -m json.tool"
```

### 2.4 Когда найдётся реальный API

Прописать в env:
```
WATER_LEVEL_SCRAPE_ENABLED=true
WATER_LEVEL_SCRAPE_SOURCE=allrivers   # или новое имя
WATER_LEVEL_SCRAPE_PAGE_URL=https://example.com/...
WATER_LEVEL_SCRAPE_GAUGE_ID=12345
```

Перезапустить:
```bash
cd ~/fishing-forecast && docker compose -f docker-compose.yml -f docker-compose.stage.yml up -d --force-recreate api
```

Триггер вручную (опционально):
```bash
curl -X POST -H "Authorization: Bearer $TOKEN" https://kvh-forecast.ru/v1/admin/ingest/water-level
```

Если новый источник не allrivers, нужно реализовать класс
наследник `WaterLevelSource` в `backend/app/water_level_sources.py`
и добавить в `create_source_from_settings()`.

---

## 3. Push-уведомления

### 3.1 Сгенерировать VAPID-ключи (один раз)

```bash
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T api python -m app.push_vapid'
```

Output копируется в `~/fishing-forecast/.env.stage`:
```
VAPID_PUBLIC_KEY_B64=BNJX...
VAPID_PRIVATE_KEY_PEM='-----BEGIN PRIVATE KEY-----\n...'
```

И в `.env.stage.example` (то, что compose реально загружает).
Force recreate:
```bash
cd ~/fishing-forecast && docker compose -f docker-compose.yml -f docker-compose.stage.yml up -d --force-recreate api
```

### 3.2 Проверить что push enabled

```bash
ssh drumd@100.106.177.127 'curl -s http://127.0.0.1:8000/v1/push/vapid-public-key'
```

Ожидаем `{"public_key":"BNJX...","enabled":true}`. Если `enabled:false`
— ключи не подгрузились в env (см. compose mode).

### 3.3 Прогнать end-to-end smoke

```bash
ssh drumd@100.106.177.127 'python3 /home/drumd/fishing-forecast/scripts/push_smoke.py'
```

Создаёт fake-подписку, проверяет round-trip, триггерит ingest и
видит outcome dispatch-а, удаляет подписку.

### 3.4 Перечитать активные подписки

```bash
TOKEN=$(...auth login...)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/v1/push/subscriptions/me | python3 -m json.tool
```

---

## 4. База данных

### 4.1 Текущая ревизия миграций

```bash
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T api alembic current'
```

Должен быть `20260427_0011 (head)` (на момент написания).

### 4.2 Применить новые миграции

```bash
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T api alembic upgrade head'
```

Идемпотентно — можно вызывать сколько угодно.

### 4.3 Откат на одну миграцию

```bash
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T api alembic downgrade -1'
```

⚠️ Только если уверены что downgrade-функция в файле миграции корректна.

### 4.4 Бэкап вручную

```bash
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  ts=$(date +%Y%m%d_%H%M%S) && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T db \
    pg_dump -U forecast -d forecast -Fc > backups/db/forecast_$ts.dump'
```

Cron уже делает это в 03:00 ежедневно (см. `crontab -l`),
ретеншн 30 дней. Файлы: `~/fishing-forecast/backups/db/forecast_*.dump`.

### 4.5 Восстановление из бэкапа

```bash
# В подключённом контейнере db:
docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T db \
  pg_restore -U forecast -d forecast -c < backups/db/forecast_20260420_030000.dump
```

⚠️ `-c` дропает существующие таблицы. Делать только в полном восстановлении.

### 4.6 Прямой psql-доступ

```bash
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml exec db \
    psql -U forecast -d forecast'
```

Полезные запросы:
```sql
-- Сколько строк weather_snapshots по зонам и дням
SELECT zone, COUNT(*) FROM weather_snapshots GROUP BY zone ORDER BY zone;

-- Свежесть water_level_readings
SELECT day, level_m, source, recorded_at FROM water_level_readings ORDER BY day DESC LIMIT 10;

-- Подписки на push
SELECT user_id, scope_zone, scope_species, conditions_json FROM push_subscriptions;

-- Замеры воды от пользователей
SELECT user_id, measured_at, zone, surface_temp_c, thermocline_depth_m
  FROM water_temp_readings ORDER BY measured_at DESC LIMIT 20;
```

---

## 5. Деплой

### 5.1 Только backend код

```bash
# Локально, в worktree:
scp backend/app/*.py drumd@100.106.177.127:/home/drumd/fishing-forecast/backend/app/
scp backend/requirements.txt drumd@100.106.177.127:/home/drumd/fishing-forecast/backend/
# Если изменены миграции:
scp backend/alembic/versions/*.py drumd@100.106.177.127:/home/drumd/fishing-forecast/backend/alembic/versions/
# Если изменены тесты:
scp backend/tests/*.py drumd@100.106.177.127:/home/drumd/fishing-forecast/backend/tests/

# Rebuild + restart:
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml build api && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml up -d --force-recreate api'

# Apply migrations + run tests:
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T api alembic upgrade head && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T api pytest tests/ -q'
```

### 5.2 Только frontend (web/)

```bash
scp web/src/App.jsx web/src/styles.css web/src/main.jsx drumd@100.106.177.127:/home/drumd/fishing-forecast/web/src/
scp web/public/sw.js drumd@100.106.177.127:/home/drumd/fishing-forecast/web/public/sw.js
scp web/index.html web/vite.config.js web/package.json web/package-lock.json drumd@100.106.177.127:/home/drumd/fishing-forecast/web/

ssh drumd@100.106.177.127 'cd ~/fishing-forecast/web && npm run build'
```

Nginx подхватывает `web/dist/` автоматически (read-only volume mount).
Никакой перезагрузки nginx не нужно.

### 5.3 Mobile-web (PWA)

```bash
scp mobile-web/index.html mobile-web/app.js mobile-web/styles.css mobile-web/sw.js mobile-web/manifest.webmanifest \
  drumd@100.106.177.127:/home/drumd/fishing-forecast/mobile-web/
```

Тоже volume mount — изменения видны сразу.

---

## 6. Мониторинг и здоровье

### 6.1 Health checks

```bash
# Public:
curl -sk https://kvh-forecast.ru/v1/ready
curl -sk https://kvh-forecast.ru/health
# Internal docker:
ssh drumd@100.106.177.127 'curl -s http://172.17.0.1:8000/v1/ready'
```

`{"status":"ready","env":"stage","db":"up","redis":"up"}` — всё хорошо.
`db: down` или `redis: down` — проверь контейнеры:

```bash
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml ps'
```

### 6.2 Docker логи

```bash
# Последние 100 строк api
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml logs --tail=100 api'

# Стрим в реальном времени:
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml logs -f api'

# Только ошибки:
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml logs --tail=200 api 2>&1 | grep -iE "error|exception|trace"'
```

### 6.3 DQ check (свежесть и полнота weather)

```bash
TOKEN=$(...auth...)
curl -s -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/v1/admin/dq/weather | python3 -m json.tool
```

Hot статус `"ok"`. Если `"degraded"` — посмотри `checks.freshness.age_hours`,
`checks.completeness.missing_days`, `checks.range.issues`,
`checks.duplicates.unique_days`.

### 6.4 Метрики через Prometheus

`prometheus` контейнер уже работает на `:9090`, scrape-эндпоинты:
- `node-exporter:9100` — метрики хоста
- `postgres-exporter:9187` — метрики DB

Grafana на `:3000` (если запущена). Дашборды нужно настраивать руками.

---

## 7. Troubleshooting

### 7.1 Страница рендерит чёрный фон

**Симптом**: `https://kvh-forecast.ru/` загружается, тёмный фон, ничего не видно.

**Диагностика**:
```bash
scp scripts/diagnose_live.py drumd@100.106.177.127:/tmp/
ssh drumd@100.106.177.127 'python3 /tmp/diagnose_live.py'
```

Скрипт сравнивает поля API с ожиданиями фронта. Самые частые
причины:
1. **Backend старее фронта**: API возвращает поля без `surface_pressure_hpa`,
   `thermocline_depth_m` и т.д. Решение: bulk-rsync backend →
   `docker compose build api && up -d --force-recreate`.
2. **VAPID не загружен**: фронт пробует `getSubscription()` и падает.
   Проверь `/v1/push/vapid-public-key`.
3. **Stale Service Worker** на клиенте: DevTools → Application →
   Service Workers → Unregister, затем Ctrl+Shift+R.

### 7.2 API 5xx на любом запросе

```bash
# Логи api
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml logs --tail=50 api'
```

Часто — пропущенные миграции при обновлении кода:
```bash
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T api alembic upgrade head'
```

### 7.3 Auto-scraper уровня воды постоянно `no_data`

Это **ожидаемое поведение** — публичного API для уровня КВХ не
существует (см. `PROJECT_REPORT.md` секция 11). Manual upsert +
climatology — operational solution. Если найден реальный source,
см. секцию 2.4.

### 7.4 Push не доходят

1. Проверь VAPID enabled: `curl /v1/push/vapid-public-key`.
2. Проверь подписку не expired: пользователь должен переподписаться
   через UI.
3. Логи dispatcher после ingest:
   ```bash
   docker compose ... logs api | grep push_dispatch
   ```
4. Тест отправки одной подписке:
   ```bash
   curl -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/v1/push/test
   ```
   `status: "no_subscription"` → пользователь не подписан.
   `status: "ok"` → push отправлен в browser-сервер (не гарантия что
   доставлен на устройство).
   `status: "failed"` → endpoint expired (404/410) или VAPID невалидный.

### 7.5 Cron ничего не делает по утрам

```bash
ssh drumd@100.106.177.127 'crontab -l | grep kvh-cron-daily'
```

Если строки нет — установить (см. 1.3).

```bash
ssh drumd@100.106.177.127 'ls -la ~/fishing-forecast/scripts/kvh-cron-daily.sh'
```

Должна быть `chmod +x`. Если нет:
```bash
ssh drumd@100.106.177.127 'chmod +x ~/fishing-forecast/scripts/kvh-cron-daily.sh'
```

Проверь логи системного крона:
```bash
ssh drumd@100.106.177.127 'sudo journalctl -u cron --since "yesterday" | grep kvh'
```

### 7.6 «Container is restarting» на api

```bash
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && \
  docker compose -f docker-compose.yml -f docker-compose.stage.yml logs --tail=30 api'
```

Самое частое: `ImportError` или `AttributeError` — обычно из-за
несинхронизированного кода (часть файлов обновлена, часть нет).
Bulk-rsync всех `backend/app/*.py` решает.

---

## 8. CI/CD

### 8.1 GitHub Actions

URL: `https://github.com/Druuumd/fishing-forecast/actions`

Workflow `.github/workflows/ci.yml` запускается на push/PR в
`main`/`develop`. Два параллельных job-а:

**`backend`**:
1. `pip install -r requirements.txt`
2. `python -m compileall app alembic/versions`
3. `pytest tests/ -v --tb=short --strict-markers`

**`web`**:
1. `npm ci`
2. `npm run build`
3. Upload `web/dist` как artifact (retention 7 дней)

Кеш: pip по hash от `requirements.txt`, npm по hash от
`package-lock.json` — тёплые билды занимают ~30 секунд.

### 8.2 Перезапуск failed CI

GitHub UI → Actions → failed run → "Re-run all jobs". Или push
пустой коммит:
```bash
git commit --allow-empty -m "ci: rerun"
git push
```

### 8.3 Что считается ломающим изменением

* Новая колонка в schema — нужна миграция.
* Новый required field в Pydantic schema — нужна frontend-правка.
* Изменение signature `_score_with_factors` — нужны тесты.
* Изменение env-vars — нужно обновить `.env.stage.example`.

---

## 9. Создание новой фичи (чек-лист)

При добавлении нового фактора скоринга / нового warning / нового
endpoint:

1. **Тест первым**. Add `backend/tests/test_<feature>.py` с TDD-style
   case-ами для happy path + boundary + error.
2. **Реализация в backend**. Pure module если возможно (`pure_function(args) -> result`).
3. **Migration** (если меняется DB):
   ```bash
   docker compose ... exec -T api alembic revision -m "your description"
   # отредактировать сгенерированный файл, добавить SQL в upgrade/downgrade
   docker compose ... exec -T api alembic upgrade head
   ```
4. **Pydantic schema** в `app/schemas.py`.
5. **Endpoint** в `app/main.py`.
6. **Прогон тестов** локально:
   ```bash
   docker compose ... exec -T api pytest tests/ -v
   ```
7. **Frontend интеграция**:
   - `web/src/App.jsx` или `mobile-web/app.js`
   - CSS если нужно
   - `npm run build` (web)
8. **Деплой** (см. секцию 5).
9. **Live verify** через `scripts/diagnose_live.py` или ручной curl.
10. **PR + CI** (на GitHub workflow прогонит ту же проверку).
11. **Update `docs/PROJECT_REPORT.md`** если изменения значимые
    архитектурно.

---

## 10. Контакты и ссылки

* Production: `https://kvh-forecast.ru/`
* Mobile PWA: `https://kvh-forecast.ru/mobile/`
* API base: `https://kvh-forecast.ru/v1/`
* Repo: `https://github.com/Druuumd/fishing-forecast`
* CI: `https://github.com/Druuumd/fishing-forecast/actions`
* Хост: `fazendaserv` (Tailscale `100.106.177.127` / LAN `192.168.0.250`)
* Docker compose root: `~/fishing-forecast/`
* Логи cron: `~/fishing-forecast/logs/`
* DB бэкапы: `~/fishing-forecast/backups/db/`

Документация:
* `docs/PROJECT_REPORT.md` — полный отчёт по архитектуре проекта
* `docs/RUNBOOK.md` — этот файл
* `docs/API.md` — API reference (готовится)
