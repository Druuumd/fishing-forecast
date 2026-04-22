# Окончательный план разработки Fishing Forecast MVP

## Цель
Собрать и выпустить self-hosted MVP сервиса прогноза рыбалки с мобильным клиентом, управляемым качеством данных, базовой безопасностью и контролируемым релизом.

## Scope MVP (заморозка)
В MVP входят:
- прогноз на 7 дней;
- отправка уловов;
- базовая авторизация;
- push-уведомления по порогу;
- карта с ограниченным набором заливов.

В Post-MVP остаются:
- социальная лента;
- продвинутые модели (LSTM/TFT);
- IoT-датчики;
- расширенная персонализация.

## Фазы и gate-критерии

### Фаза A. Foundation & Governance (0.5 недели)
- Утвердить ADR по auth, cache, retrain policy, backup policy.
- Зафиксировать SLO/SLA:
  - API uptime >= 99%;
  - p95 `GET /forecast` <= 250ms, cache-hit <= 30ms;
  - свежесть прогноза <= 24h.
- Подготовить security/compliance baseline.

Gate A:
- утверждены ADR;
- заполнен реестр рисков;
- определены DOR/DOD для задач MVP.

### Фаза 1. Инфраструктура и сервер (1-2 недели)
- Базовая инфраструктура и hardening:
  - UFW, fail2ban, non-root policy, автообновления безопасности;
  - разделение `stage/prod` (и `dev` при наличии ресурса);
  - health/readiness checks.
- Централизованные JSON-логи с trace-id.

Gate 1:
- стабильный запуск после reboot;
- внешняя доступность API;
- пройден security baseline.

### Фаза 2. Data Platform (2-4 недели)
- Ingestion: Open-Meteo, ERA5, scraper воды, moon calc.
- DQ-пайплайн:
  - freshness/completeness/range/duplicate checks;
  - алерты при сбое ingestion больше 1 цикла.
- Data contracts ingestion -> storage -> features.

Gate 2:
- 14 дней без критических пропусков;
- DQ-отчет стабильно зеленый.

### Фаза 3. ML + API (4-6 недели)
- Feature engineering и baseline-модель для `pike`/`perch`.
- Метрики качества:
  - MAE/RMSE;
  - Spearman не ниже утвержденного порога;
  - top-day hit-rate на лучших 20% днях.
- API:
  - `GET /forecast` с кэшем и graceful degradation;
  - `POST /catch` с валидацией, rate limiting, anti-spam.
- Retrain policy с минимальным объемом и контролем стабильности распределений.

Gate 3:
- стабильный API-контракт;
- пройден нагрузочный smoke;
- метрики лучше baseline.

### Фаза 4. Mobile App (5-8 недели)
- Прогноз, погодные детали, журнал уловов, карта, auth, push.
- UX:
  - confidence и объяснение прогноза;
  - empty states, offline/online переходы, retry UX.
- Telemetry:
  - crash reporting;
  - производительность экранов;
  - ключевые продуктовые события.

Gate 4:
- beta проходит реальные сценарии offline/poor network/first-run/auth-fail.

### Фаза 5. Quality, Release, Operations (8-10 недели)
- Unit + integration + e2e smoke по критичным сценариям.
- CI/CD stage -> prod с rollback playbook.
- Техметрики и продуктовые KPI:
  - `daily_active_users`;
  - `forecast_open_rate`;
  - `catch_submit_success_rate`.
- Backup и регулярный restore drill.

Gate 5 (Go-Live):
- выполнены release criteria;
- проведен dry-run инцидента и восстановления.

## Риски и превентивные меры
- Один HTML-источник температуры воды -> fallback + ручной override + alert.
- Cold-start моделей -> conservative scoring + confidence-маркировка.
- Низкая дисциплина ввода уловов -> UX-валидации + антиспам + мягкая геймификация.
- Ограниченный ресурс команды -> жесткий scope freeze после середины Фазы 4.

## Реалистичный график
- Недели 1-2: Foundation + Infra.
- Недели 2-4: Data ingestion + DQ + historical init.
- Недели 4-6: ML baseline + API v1.
- Недели 5-8: Mobile v1 параллельно стабилизации API.
- Недели 8-10: QA + release prep + operations handover.
