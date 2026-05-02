# KVH Forecast — отчёт по проекту

*Обновлено: 2026-04-30 — раздел 12 (UI/UX) и 18 (UI overhaul) перерисованы под новую визуальную систему*

---

## 1. Назначение и видение

**KVH Forecast** — служба прогнозирования активности клёва рыбы на
**Красноярском водохранилище** (КВХ) с фокусом на трёх целевых видов:
**щука, окунь, лещ**. Сервис собирает максимум данных о текущих
гидрометеорологических и биологических условиях, прогоняет их через
видоспецифичную скоринг-модель и возвращает:

* **взвешенную оценку клёва** на текущий день и на 7 дней вперёд,
* **разложение оценки на факторы** (физика, объяснимая модель),
* **временные окна суточной активности** (зорьки + лунные пики),
* **предупреждения** о неблагоприятных событиях (гроза, шторм,
  опасный лёд, нерестовый запрет, нерест отдельных видов),
* **рекомендации по глубине ловли** через термоклинную модель,
* **зональные данные** по 13 заливам акватории.

Работает как двухканальный продукт: **React-веб** на
`https://kvh-forecast.ru/` и **vanilla-JS PWA** на `/mobile/` для
установки на смартфон с offline-кешем.

---

## 2. Стек и развёртывание

### Backend

* **Python 3.12 + FastAPI 0.115** — REST API
* **PostgreSQL 16** — основное хранилище (catch records, weather
  snapshots, water level, push subscriptions, water-temp readings)
* **Redis 7** — кеш форекаста (TTL 5 мин), rate-limiting улова
* **SQLAlchemy 2.0 + Alembic** — ORM и миграции
* **PyJWT** — аутентификация
* **PyEphem** — лунные эфемериды для solunar-окон
* **PyWebPush + cryptography** — Web Push (VAPID)
* **Pytest** — 178 регрессионных тестов

### Frontend

* **web/** — React 18 + Vite, единственный SPA-bundle ~187 KB
  (60 KB gzip), вкладочный интерфейс, SVG-чарты, Leaflet-карта (CDN)
* **mobile-web/** — vanilla JS PWA, ~58 KB JS, 13 KB HTML, тот же
  визуальный язык, устанавливается через manifest.webmanifest

### Инфраструктура

* **Docker Compose** на `fazendaserv` (Tailscale 100.106.177.127, IPv4 192.168.0.250)
* **Caddy** — TLS-терминация, маршрутизирует `kvh-forecast.ru` →
  `fishing-forecast-nginx` (порт 8081)
* **fishing-forecast-nginx** — отдаёт `/` (React `web/dist`) и
  `/mobile/` (mobile-web) + проксирует `/v1/*` → API
* **GitHub Actions CI** — параллельные jobs: backend pytest +
  frontend vite build с pip/npm-кешем
* **Cron daily 03:10 KRSK** — `~/fishing-forecast/scripts/kvh-cron-daily.sh`
  логинится → ingest weather → DQ → ML retrain, лог в
  `~/fishing-forecast/logs/kvh-daily-YYYY-MM-DD.log` с 14-дневным retention

---

## 3. Источники данных

| Источник | Что даёт | Статус |
|----------|----------|--------|
| **Open-Meteo** (free) | температура воздуха, MSL давление, ветер, облачность, осадки, влажность, sunrise/sunset, daylight, hourly pressure | работает, fetch на каждый из 13 заливов отдельно |
| **temperaturavody.com** | наблюдённая + прогнозная температура воды (32 + 7 дней) | работает, scrape regex-ом |
| **Open-Meteo Marine** | sea surface temp (фоллбек) | используется, но приоритет ниже observed |
| **Уровень воды (open API)** | — | **не существует**: проверены allrivers / rushydro / FAVR / GMVO / ENBVU — ни один не отдаёт reservoir-level публично. Framework `WaterLevelSource` готов, allrivers-стаб с extraction Bearer-token — на случай если оператор найдёт зацепку |
| **Уровень воды (manual)** | админский upsert через `POST /v1/admin/water-level` | работает, текущий primary source |
| **Климатология** | sin-сглаженная месячная модель уровня (NPU 243 → УМО 226 м) | fallback когда нет fresh manual |
| **Пользовательские замеры** | surface_temp_c + thermocline_depth_m + below_thermocline_temp_c с GPS | работает, валидация по bbox + диапазонам |
| **PyEphem (DE405)** | реальные эфемериды Солнца и Луны | используется для solunar-окон |

---

## 4. Скоринг-модель

### 4.1 Гибридная формула

```
final_score = clamp(additive_score × Π(gate_multipliers), 0, 5)
```

* **Additive score** — сумма факторов с base-значением профиля и
  весовыми вкладами (water_temp, pressure, moon, wind, cloud,
  precipitation, daylight, water_level, ice_regime, thermocline,
  zone_bias, season, species_spawn, ml_bias).
* **Multiplicative gates** — нелинейные «дисквалифицирующие»
  условия в [0.3, 1.0]: pressure_shock, severe_weather,
  thermal_shock. Гасят итоговый score когда срабатывают; в карточке
  показываются как факторы с особым оформлением (⚡ красная полоса,
  detail с множителем `×0.63`).

Дизайн отвечает реальности: при резком скачке давления +8 hPa/24h
рыба «закрывает рот» вне зависимости от того, насколько хороши
прочие условия. Гейты делают score = 0.7 даже на летнем дне с
тёплой водой и стабильной луной — что соответствует ловецкому опыту.

### 4.2 Видовые профили

Каждый из трёх видов имеет свой `_species_profile`:

| Параметр | Pike | Perch | Bream |
|----------|------|-------|-------|
| Base | 2.8 | 2.5 | 2.4 |
| Tw_optimal | 10°C (Krsk) / 12 (default) | 13 / 15 | 19 / 20 |
| Tw_tolerance | 8 / 9 | 13 / 9 | 7.5 / 10 |
| Pressure_optimal (surface hPa) | 986 (Krsk@234m) | 988 | 988 |
| Pressure_trend pref | -0.6 (slight falling) | 0 (stable) | 0 |
| Moon preferred | 0.5 | 0.35 | 0.8 (bright nights) |
| Cloud_optimal | 70% | 40% | 55% |
| Daylight_optimal | 13h | 13.5h | 16h (long Siberian summer) |

### 4.3 Барометрическое уточнение

Open-Meteo отдаёт MSL давление. На высоте уреза воды КВХ ~234 м
реальное давление, которое «ощущает» рыба, на ~27-32 hPa ниже.
Скоринг работает в **поверхностных** hPa через стандартную
барометрическую формулу (ISA, тропосфера) с поправкой на
температуру воздуха.

UI показывает обе величины: `1014 hPa MSL → 986 hPa surface@234m`.
Это совпадает с показанием карманного барометра рыбака (740 мм рт.ст.
≈ 987 hPa) — модель «говорит на одном языке» с ловцом.

### 4.4 Восточно-Сибирские особенности

* **Ледовый режим** (open / transition / ice) выводится из температуры
  воды + месяца, с per-zone порогами (мелкие заливы встают раньше).
* **Термоклин** — фактор летней стратификации (вода >20°C).
* **Сезонный календарь Красноярска**: щука пик май + сент-окт
  (поздний нерест), лещ компактный июнь-август, окунь круглый год
  включая лёд.
* **Высокий зимний антициклон** (1025-1040 hPa) — оптимум давления
  сдвинут вверх и толерантность шире.

### 4.5 Гейты (multiplicative)

| Гейт | Триггер | Floor по видам | Биологическое обоснование |
|------|---------|----------------|---------------------------|
| `pressure_shock_gate` | \|ΔP/24h\| ≥ 3 hPa | pike 0.45, perch 0.35, bream 0.30 | Барический шок. Carp-family и percids чувствительнее; щука как opportunist менее |
| `severe_weather_gate` | wind ≥ 10 m/s + precip ≥ 8 mm | 0.40 | Штормовая мелочь не может питаться, столб воды перемешан |
| `thermal_shock_gate` | bream <8°C / pike <2°C / perch >24°C | 0.30 / 0.55 / 0.60 | Видовые пороги физиологии |

Confidence уменьшается пропорционально худшему гейту:
`conf = base_conf × (0.5 + 0.5 × min_gate)`. UI отображает
`уверенность 45%` — рыбак понимает что на этом дне модель сама
не уверена.

### 4.6 Видовые нерестовые окна (`species_spawning.py`)

Модуль определяет фазу для каждого вида по комбинации **календарь
+ температура воды** (физиологический триггер):

| Вид | Pre-spawn (Tw) | Active (Tw) | Post (Tw) | Calendar |
|-----|----------------|-------------|-----------|----------|
| Pike | 2-4°C | 4-9°C | 9-11°C | Apr-May |
| Perch | 4-7°C | 7-12°C | 12-14°C | Apr-May |
| Bream | 8-12°C | 12-18°C | 18-20°C | May-Jun |

Score-фактор `species_spawn` дает **+0.20 на pre-spawn** (легендарный
весенний жор), **−0.55 на active** (рыба не ест), **−0.20 на post**
(восстановление).

Каскад фаз по сезону (синтетика):
```
2026-04-15 Tw=2.5  pike: pre   perch: none  bream: none
2026-04-30 Tw=5.0  pike: active  perch: pre   bream: none
2026-05-10 Tw=8.0  pike: active  perch: active bream: pre
2026-05-20 Tw=11   pike: post    perch: active bream: pre
2026-05-30 Tw=14   pike: none    perch: post   bream: active
2026-06-05 Tw=17   pike: none    perch: none   bream: active
2026-06-15 Tw=20   pike: none    perch: none   bream: post
2026-06-25 Tw=22   все обычно
```

---

## 5. Зональная модель — 13 заливов

КВХ ~388 км вытянутая акватория с заметно разными
гидротермальными режимами. Заливы сгруппированы по 9 архетипам:

| Архетип | Глубина | Прогрев | Ice | Заливы |
|---------|---------|---------|-----|--------|
| `shallow_warm` | мелко | +1.5°C | XI–V | syda, ubey, karasug |
| `swampy_shallow` | мелко | +0.8°C | XI–V | yezagash |
| `narrow_shallow` | мелко | +0.5°C | XI–V | anash, koma |
| `medium_balanced` | средне | 0 | XI–IV | ogur, izhul |
| `irregular_mixed` | переменно | +0.2°C | XI–IV | derbino |
| `steep_cool` | средне-глубоко | -0.6 | XI–IV | sisim |
| `rocky_deep_cool` | глубоко | -0.8 | XI–IV | biryusa |
| `deep_cold` | глубоко | -1.2 | XI–IV | tubinsky |
| `main_channel` | очень глубоко | -1.5 | XII–IV | main_channel |

Каждая зона имеет:
* `water_temp_offset_c` — смещение Tw от базовой
* `ice_freeze_temp_c` / `ice_thaw_temp_c` — пороги ледообразования
* `ice_months` / `transition_months` — месячные окна
* `level_sensitivity` — множитель (мелкие реагируют ×1.5, глубокие ×0.7)
* `species_base_bias` — habitat suitability per species
* `archetype` — для thermocline_advisory
* координаты центра (используются для per-zone Open-Meteo fetch)

### 5.1 Per-zone Open-Meteo

При daily ingest делается **отдельный API-вызов на координаты
каждого залива**. В DB лежат снапшоты с composite PK `(day, zone)`
плюс `default` для общего обзорного режима. Когда фронт спрашивает
`/v1/forecast?zone=biryusa`, модель использует именно бирюсинские
данные погоды; эвристический Δ°C автоматически отключается, так как
вода теперь зональная.

Различие в одной точке времени:

```
Сыда (south, shallow):  air +7.5°C, wind 3.3 м/с, clouds 75%, ΔP +6.2
Дербино (central):      air +6.8°C, wind 4.7 м/с, clouds 84%, ΔP +6.1
Бирюса (NE):            air +7.1°C, wind 3.5 м/с, clouds 56%, ΔP +6.9
Главное русло:          air +7.1°C, wind 4.9 м/с, clouds 69%, ΔP +6.2
```

Это **реальные** 4 разных микроклимата — не аппроксимация.

---

## 6. Termocline advisory

Пер-зональная heuristic-модель термоклина:

```
strength = (Tw_surface − 12)/10 × strat_capacity_by_archetype
depth_m = base_depth_archetype + ⌊(Tw − 14) × 0.4⌋
recommended_depth_m = depth_m − 2
```

Где `strat_capacity` колеблется от 0.20 (yezagash, мелководный
заболоченный — практически не стратифицируется) до 1.00
(main_channel — устойчивая стратификация).

UI показывает SVG-схему: тёплый жёлтый верх, красная горизонтальная
линия термоклина, синий холодный низ, зелёная пунктирная отметка
рекомендованной глубины приманки. Текстовый совет: «Плотный
термоклин ~13 м. Поверхностная ловля бесполезна. Троллинг/отвес на
11–13 м, бровки и свалы.»

### 6.1 Пользовательские замеры (источник для будущей ML-модели)

`POST /v1/water-temp-readings` принимает:
* GPS (валидируется по bbox 53–56°N, 90.5–93.5°E)
* surface_temp_c (0–30°C)
* thermocline_depth_m (1–60 м, опционально)
* below_thermocline_temp_c (1–10°C, **строго ниже** surface, опционально)
* instrument, note
* freshness ±30 дней

При отсутствии одной из (depth, below_temp) валидатор **отказывает**
с field_errors — нужен полный тепловой профиль для будущего обучения.

Auto-zone-detection через haversine до центра ближайшего залива
(≤25 км → bay code, иначе main_channel).

UI для submission: форма с подсветкой полей при ошибке, Leaflet-карта
с pinами заливов (серые) и существующих замеров (цвет по surface_temp
от тёмно-синего <5°C до красного ≥25°C), клик по карте подставляет
координаты.

**ML-roadmap**: когда наберётся ≥30 замеров на залив, обучить
регрессию `(zone, surface_temp, day_of_year, recent_wind_avg) →
(thermocline_depth_m, below_temp_c)`. Сейчас heuristic используется
безусловно; при наличии fresh данных она будет автоматически
заменена observed-моделью per-zone.

---

## 7. Адаптивные предупреждения

`/v1/warnings` отдаёт активные warnings, рассчитанные на сегодняшний
прогноз:

| Код | Severity | Триггер |
|-----|----------|---------|
| `pressure_shock` | warn | gate активен в next 3 days |
| `severe_weather` | danger | gale + downpour одновременно |
| `gale_wind` | warn | wind ≥ 12 m/s |
| `heavy_rain` | warn | precip ≥ 8 mm |
| `ice_unsafe` | danger | regime = transition (тонкий лёд) |
| `drawdown_alarm` | warn | уровень упал >1 м за 7 дней |
| `spawning_ban` | info | в окне 25.04–25.06 (приказ Минсельхоза №226) |
| `pike_spawning` | info | active/post phase для щуки |
| `perch_spawning` | info | то же для окуня |
| `bream_spawning` | info | то же для леща |

Spawning ban даты настраиваются через env-vars
`SPAWNING_BAN_START_MD` / `SPAWNING_BAN_END_MD` (формат `MM-DD`)
без перекомпиляции — на случай поправок в правилах.

UI рендерит как цветные карточки (красные / оранжевые / синие) над
прогнозом, с dismiss-кнопкой и 24-часовым TTL в localStorage,
чтобы пользователь не видел одно и то же предупреждение каждый час.

---

## 8. Solunar окна (PyEphem)

`backend/app/solunar.py`:

```python
compute_solunar_periods(target_date, lat, lon, elevation_m=234.0)
  → {major: list[{start, end, label}],
     minor: list[{start, end, label}],
     quality: 0..1}
```

* **Major windows** ±1ч вокруг **upper transit** (зенит) и
  **lower transit** (надир) — рассчитываются `obs.next_transit(moon)`
  и `obs.next_antitransit(moon)`.
* **Minor windows** ±30мин вокруг **moonrise** и **moonset** —
  `obs.next_rising` / `obs.next_setting`.
* **Quality** = `abs(illumination − 50) / 50` — пик 1.0 в новолуние
  и полнолуние, минимум 0 в первой/последней четверти.

`ForecastService.best_hours` объединяет solunar окна с dawn/dusk
(±1ч вокруг sunrise/sunset). UI показывает 24-часовую горизонтальную
шкалу с цветовыми блоками по типу окна (золотой dawn/dusk,
голубой major, фиолетовый minor) и шкалой intensity.

Каскад во времени: каждый день moon transit сдвигается ~42 мин
(соответствует лунному дню 24ч50мин). Длительность окна Major = 2ч
жёстко; Minor = 1ч.

---

## 9. Лунные фазы

`backend/app/moon_phase.py` декомпозирует raw `moon_phase` (0..1)
во:

* `age_days` (0..29.53)
* `illumination_pct` (через cos)
* `phase_kind` ∈ {new, waxing_crescent, first_quarter, waxing_gibbous,
  full, waning_gibbous, last_quarter, waning_crescent}
* `phase_label` (русская строка для UI)
* `growing` (растущая/убывающая)

Эти поля присутствуют в каждом ForecastDay для отображения в карточке
(«🌖 Растущая (горбатая) · 71%»).

---

## 10. Push-уведомления — конструктор

### 10.1 Архитектура

Подписка теперь — **конструктор условий**, а не один порог. Каждая
подписка несёт:

* `endpoint` + ключи (Web Push transport)
* `name` (метка пользователя для своего удобства)
* `scope_zone`, `scope_species` (что именно отслеживать)
* `conditions[]` — список `{type, params}` объектов

Дисциплина dispatcher-а: для каждой подписки прогоняем все условия
против каждого из next 5 forecast-дней; если ВСЕ условия true И
день не равен `last_notified_for_day` — отправляем push, обновляем
дедуп-маркер.

### 10.2 15 типов условий в `CONDITION_REGISTRY`

| Type | Параметр | Семантика |
|------|----------|-----------|
| `score_min` | min (def 3.5) | оценка ≥ |
| `wind_max` | max_m_s (def 6) | ветер ≤ |
| `no_pressure_shock` | — | нет барического шока |
| `no_thermal_shock` | — | нет термошока |
| `no_severe_weather` | — | нет шторма |
| `no_precipitation` | max_mm (def 0.5) | сухо |
| `water_temp_min` | min (def 8) | вода прогрета |
| `water_temp_max` | max (def 24) | вода не перегрета |
| `pressure_stable` | delta_max (def 4) | стабильное давление |
| `cloud_max` | pct (def 70) | не сильно облачно |
| `daylight_min` | hours (def 12) | длинный день |
| `lookahead_max_days` | days (def 5) | в ближайшие N |
| `weekend_only` | — | только выходные |
| `moon_growing` | growing (true/false) | фаза роста луны |
| `moon_phase_in` | kinds (list) | конкретные фазы |

UI: каталог через `/v1/push/condition-types` (включая parameter
schemas), пользователь добавляет/удаляет условия в форме, каждое
условие имеет свои inputs.

### 10.3 VAPID

Сгенерированы один раз через `python -m app.push_vapid`, хранятся
в `~/fishing-forecast/.env.stage` (загружается через
`docker compose -f docker-compose.yml -f docker-compose.stage.yml`).

---

## 11. Уровень воды

### 11.1 Архитектура

* `WaterLevelReadingModel` — `(day, level_m, inflow, outflow,
  source, note, recorded_at)`
* `WaterLevelRepository` — upsert/get_latest/get_window
* `WaterLevelService` — `current_state(today)` возвращает aggregate с:
  * latest reading,
  * 7-day trend (latest − 7d_ago_reading или vs. climatology),
  * `is_fresh` (≤14 дней),
  * fallback на climatology если no fresh.

Климатология: sin-сглаженная между 12 месячными средними значениями
для КВХ (NPU 243.0 = норма летом, УМО 226.0 = late-winter drawdown,
median 234.0 = reservoir reference elevation).

### 11.2 Фактор водного уровня в score

Видоспецифичная функция:
* **Лещ** — сильно негативно при падении уровня (рассеивает стаи),
  бонус при стабильном
* **Щука** — позитивно при росте (заходит на затопленные мели для
  охоты), мягко негативно при падении
* **Окунь** — слабо чувствителен; штраф только при больших
  колебаниях (>0.5 м/неделю)

**Региональная коррекция**: весеннее падение март-май для КВХ
**норма** (sezonal drawdown), штраф мягче в 2.5 раза. Зато
аномальное падение в июле-августе для леща усилено до −0.45.

### 11.3 Auto-scraper framework

`WaterLevelSource` ABC + `AllRiversWaterLevelSource` стаб с
trick-ом извлечения Bearer-token из inline JS на странице.
**Не работает в production** потому что **публичного API для
уровня КВХ не существует**:

* allrivers.info — гидропосты только в Енисее ниже плотины
* rushydro.ru — WAF блокирует non-browser UA
* gmvo.skniivh.ru / enbvu.ru / gis.favr.ru — нет open-data

Когда оператор найдёт source, новая `WaterLevelSource` реализация
прописывается через env-var `WATER_LEVEL_SCRAPE_SOURCE=имя` и
плагин подключается без изменений в основной код.

---

## 12. UI / UX

### 12.1 Web (React)

**Вкладки** (с emoji-иконками для быстрого скана):
🎣 Прогноз · 📈 История · 🐟 Улов · 🌡 Замеры · 🔔 Уведомления ·
👤 Профиль · ⚙️ Настройки · ✅ Согласия · 🛡 Приватность

**Прогноз**:
* Hero-карточка для «Сегодня» — широкая, с gradient-фоном, increased
  типографикой, визуальный акцент через CSS pseudo-полосу
* Score = 5 fish-иконок 🐟 заполненных пропорционально + цифра
  + emoji-вердикт (🔥 / 👍 / 🤔 / 🙁 / 🚫) + словесный label
* Borders по 5 уровням: excellent/good/fair/weak/bad
* Friendly-даты: «Сегодня», «Завтра», «Чт 30 апр»
* Список факторов **сворачивается** до high-impact (\|contribution\| ≥ 0.15)
  + всех гейтов; «+ ещё N факторов» раскрывает остальное
* Banner предупреждений (severity-coded) над карточками
* Banner уровня воды (текущий + 7d trend + источник)
* Per-day: best-hours strip (24h), thermocline diagram, day-meta grid,
  factor list с гейт-подсветкой

**История**:
* 4 SVG-чарта (sparkline) со shimmer-плейсхолдерами при загрузке
* Уровень воды (с НПУ/УМО reference lines)
* Tw воды + воздуха
* Давление MSL + surface
* Ветер + осадки
* Stats summary (записей / текущий / Δ за период / мин-макс)
* Список последних уловов залогиненного пользователя

**Замеры воды**:
* Forma submission с field-level errors (красная подсветка inputs)
* Leaflet-карта OSM с маркерами 13 заливов + замеров (цвет по Tw)
* Клик по карте → подставляет координаты в форму
* GPS-кнопка
* Список последних замеров всех пользователей

**Уведомления**:
* Каталог 15 типов условий (загружается из API)
* UI добавления условия через dropdown типов + auto-rendered inputs
  по `params_schema`
* Список активных подписок с человеко-читаемым summary

**Прочее**:
* Slim header с offline-баннером
* Loading skeletons (shimmer-анимация) при первой загрузке
* Service Worker (versioned cache `kvh-v1-static` + `kvh-v1-api`):
  network-first для GET API, cache-first для статики, offline
  fallback на SPA index

### 12.2 Mobile-web (vanilla JS PWA)

Полный паритет с web/: те же вкладки, те же графики (SVG namespace
helper), та же Leaflet-карта, те же skeleton-плейсхолдеры, тот же
Service Worker. Манифест PWA позволяет «add to home screen» —
запускается полноэкранно как нативное приложение.

---

## 13. Тестирование

**178 регрессионных тестов** в `backend/tests/`:

| Файл | Тестов | Покрывает |
|------|--------|-----------|
| `test_scoring.py` | 17 | shape `_score_with_factors`, surface pressure, все три gate с граничными значениями для каждого вида, композиция гейтов, confidence dampening, барометрическая формула |
| `test_zones.py` | 21 | 13 заливов registered, profile shape, fallback unknown→baseline, дифференциация archetype, ice freeze threshold (parametrized × 13) |
| `test_conditions.py` | 33 | 15 типов из CONDITION_REGISTRY, parametrized describe, граничные условия для каждого, gate-presence, lookahead, weekend, moon |
| `test_thermocline.py` | 13 | strength градиент, depth heuristic, archetype-зависимость, ветровая история |
| `test_warnings.py` | 24 | каждое правило warning, calendar boundaries, multi-stack, env-overridable spawning ban |
| `test_water_temp_readings.py` | 16 | bbox, ranges, surface > below, partial profile, zone-detection для 13 заливов |
| `test_species_spawning.py` | 21 | каждая фаза для каждого вида, factor contribution mapping, profile invariants |
| `test_moon_phase.py` | 10 | все 8 named фаз, illumination cosine, growing flag |
| `test_solunar.py` | 11 | structure invariants, transit chronology, longitude shift, quality at known dates |
| `test_best_hours.py` | 12 | dawn/dusk + lunar windows + intensity ordering |

**Pytest время**: 0.88 с для всего набора. CI на GitHub Actions
прогоняет в `python:3.12-slim` контейнере (no Docker required).

---

## 14. Операционные процедуры

### 14.1 Daily cron (03:10 KRSK)

Скрипт `~/fishing-forecast/scripts/kvh-cron-daily.sh`:
1. Login → bearer token
2. POST `/v1/admin/ingest/weather` (вызывает per-zone Open-Meteo + temperaturavody.com + push dispatcher)
3. GET `/v1/admin/dq/weather` (data-quality check)
4. POST `/v1/admin/ml/retrain` (best-effort, skip если <20 catch records)
5. Лог в `~/fishing-forecast/logs/kvh-daily-YYYY-MM-DD.log`
6. Авто-удаление логов старше `LOG_RETENTION_DAYS` (default 14)

### 14.2 Деплой

```bash
scp backend/app/*.py drumd@100.106.177.127:/home/drumd/fishing-forecast/backend/app/
scp backend/requirements.txt drumd@100.106.177.127:/home/drumd/fishing-forecast/backend/
scp web/src/App.jsx web/src/styles.css drumd@100.106.177.127:/home/drumd/fishing-forecast/web/src/
ssh drumd@100.106.177.127 'cd ~/fishing-forecast && docker compose -f docker-compose.yml -f docker-compose.stage.yml build api && docker compose -f docker-compose.yml -f docker-compose.stage.yml up -d --force-recreate api && docker compose -f docker-compose.yml -f docker-compose.stage.yml exec -T api alembic upgrade head'
ssh drumd@100.106.177.127 'cd ~/fishing-forecast/web && npm run build'
```

### 14.3 Миграции

Текущая alembic-цепочка:
```
20260420_0001  create_catch_records
20260421_0002  create_weather_snapshots
20260421_0003  create_ml_model_versions
20260421_0004  ml_model_publish_safety
20260421_0005  create_user_consents
20260422_0006  add_wind_inputs_to_forecast
20260423_0007  extended_weather_metrics
20260424_0008  create_water_level_readings
20260426_0009  zone_on_weather_snapshots (composite PK day+zone)
20260426_0010  create_push_subscriptions (constructor with conditions_json)
20260427_0007  expand_forecast_weather_fields
20260427_0011  create_water_temp_readings
```

`alembic upgrade head` идемпотентно докатывает все.

---

## 15. Что ещё впереди

### Краткосрочно

* **History summary upgrade** — заменить 4 stat-блока на сравнение
  «текущее vs средний за 30 дней» с дельтой в %
* **Push tab UX** — переделать список условий из формы-в-колонке в
  chip-cards (как фильтры в современных приложениях)
* **Catch tab visual polish** — подтянуть к новой визуальной системе

### Средний срок

* **ML thermocline regression** — когда наберётся ≥30 пользовательских
  замеров на залив. Регрессия `(zone, surface_temp, day_of_year,
  recent_wind_avg) → (depth, below_temp)`. Replace heuristic per-zone.
* **Wind-history factor** — последние 3 дня среднего ветра уже
  учитываются в thermocline strength; можно расширить на
  `pressure_stability_72h` для большего horizon в push-условиях.
* **Catch retrospective** — сравнение «при таких условиях ранее
  ловилось X, модель давала Y» — требует joining catch records с
  историей погоды и графика прогноза vs реальности.

### Долгосрочно

* **Per-zone water temperature** — temperaturavody.com сейчас
  reservoir-wide; в идеале нужен zone-specific source.
* **Water level scraper** — если найдётся реальный feed (Telegram-
  channel ОАО «РусГидро Красноярск», частный data dump). Framework
  готов.
* **i18n** — текущий UI чисто русский. English target для зарубежных
  гидов.

---

## 16. Метрики проекта

* **~7000 строк Python** (приложение)
* **~1300 строк JSX** (React фронт)
* **~1500 строк vanilla JS** (mobile PWA)
* **178 тестов**, 0.88 с pytest, 0 known regressions
* **15 типов push-условий** в конструкторе
* **13 заливов** с per-zone Open-Meteo и физикой
* **3 вида рыбы** с разными профилями × 13 зон = 39 уникальных
  сценариев скоринга
* **6 типов окон активности** (dawn, dusk, 2 lunar major, 2 lunar minor)
* **10 типов adverse warnings**
* **11 alembic миграций**
* **0 публичных API** для уровня воды на КВХ (после исчерпывающего
  поиска); manual + climatology — operational solution

---

## 17. Ключевые проектные решения

1. **Скоринг 0-5 со словесным вердиктом** — рыбак не должен думать
   «3.42 это хорошо?», UI сразу даёт «Хороший день для ловли 👍».
2. **Видовые профили вместо общей модели** — лещ не «то же что щука
   с другим оптимумом», у него *совсем* другая физиология. Каждый
   вид — отдельный профиль с собственными параметрами и факторами.
3. **Гибридная additive + multiplicative модель** — отвечает реальности
   что некоторые условия (барический шок) дисквалифицируют день
   независимо от прочих факторов.
4. **Объяснимая модель** — `factors[]` в API ответа разлагает score
   на компоненты с человекочитаемыми detail-строками. Пользователь
   видит почему сегодня плохо, а не просто «индекс 1.5».
5. **Per-zone Open-Meteo вместо эвристик** — реальная погода на
   координатах залива, а не «база +1.5°C для южных».
6. **Поверхностное давление вместо MSL** — рыба ощущает физическое
   давление воздуха над водой, а не astronomical reference. Карманный
   барометр и наша модель говорят на одном языке.
7. **PyEphem solunar вместо аппроксимации** — реальная орбита Луны
   обходится в +2 МБ зависимостей и точность до минуты.
8. **Конструктор push, не однопараметрический threshold** — рыбак
   формирует «свой» рецепт условий, например «пятница–воскресенье,
   щука в Сыдинском, score ≥ 4, без барического шока, ветер ≤ 8».
9. **Mobile-web vanilla JS, а не React Native** — install через
   PWA, нет app-store, мгновенный deploy через scp + npm build.
10. **Crowdsourced thermocline data** — вместо покупки оборудования
    система собирает замеры от рыбаков с эхолотом, валидирует
    жёстко, копит чистый dataset для ML regression позже.

---

## 18. UI overhaul (2026-04-30 batch)

После initial-доставки фич UI был «дебаг-инструментом», а не
консьюмерским продуктом. В двух итерациях (5 + 3 пункта) переделан
под user-first дизайн. Все изменения зеркалятся в `web/` (React) и
`mobile-web/` (vanilla JS).

### 18.1 Forecast tab

* **Hero today card** — первая карточка во всю ширину сетки, с
  gradient-фоном, увеличенной типографикой (date 22px, score 24px),
  лейблом «Сегодня · ловите момент». Псевдо-полоса слева в цвете
  tier'а (excellent/good/fair/weak/bad).
* **Score visualization** — 5 fish-иконок 🐟, заполненных
  пропорционально через CSS `--fill` маску, плюс цифра + emoji-вердикт
  (🔥 / 👍 / 🤔 / 🙁 / 🚫) + словесная label («Отличный день — пора
  собираться!»).
* **Friendly даты** — «Сегодня», «Завтра», «Чт 30 апр» вместо
  машинного `Чт 27 апр`.
* **Сворачиваемые факторы** — по умолчанию показываются только
  high-impact (\|contribution\| ≥ 0.15) + все гейты; «+ ещё N факторов»
  раскрывает остальное. Снижает визуальную перегрузку с 12-13
  параметров до 4-6.
* **Tier-borders** — 5 уровней цвета по `scoreVerdict`, не бинарные
  hot/cold.

### 18.2 History tab

* **5 stat-карточек** заменили 4 базовых stat-блока: уровень / Tw воды
  / Tw воздуха / давление / ветер. Каждая показывает текущее значение,
  среднее за период, дельту от среднего с цветной стрелкой
  (`stat-delta-good/bad/info/neutral`). Для ветра «меньше = лучше для
  ловли» (higherIsBetter=false), для остальных — neutral информационная
  раскраска.
* **Loading skeletons** — shimmer-плейсхолдеры в форме реальных
  карточек/чартов при первой загрузке вкладки.

### 18.3 Push tab

* **Chip-cards для условий** — pill-shaped тэги `<div class="condition-chip">`
  с inline-полями для параметров и `×` removal-кнопкой. Wrap по
  ширине, занимают мало места даже на мобиле.
* **Dropdown типов** теперь auto-фильтрует уже добавленные типы —
  нельзя случайно добавить два `score_min`. Если все 15 типов добавлены,
  dropdown disabled с лейблом «— все типы добавлены».

### 18.4 Catch tab

* **Species pills** — 3 равноширотных pill-кнопки с emoji-иконками
  (🐊 щука / 🐠 окунь / 🐟 лещ) вместо `<select>`. Active-состояние
  через gradient-фон.
* **Score slider** — `<input type="range">` с `accent-color: #2563eb`,
  под ним live-значение (X.X / 5) и 5-fish визуализация
  (как в forecast cards).
* **Queue-badge** — chip-ярлык «N в очереди offline» возле заголовка
  когда есть pending записи; кнопка `↻ Sync очередь (N)` показывается
  только когда queue не пуста.
* **Debug-fold** — `<details>` блок «Подробности (debug)» скрывает raw
  JSON-выводы под clickable summary, чтобы не загромождать UI обычному
  пользователю.

### 18.5 Глобальные правки

* **Slim header** — убрал API URL и `/ready`-кнопку из шапки, осталось
  только название + offline-баннер. Дебаг переехал в новую вкладку
  ⚙️ Настройки.
* **Tab icons** — emoji-префиксы для быстрого визуального скана:
  `🎣 Прогноз 📈 История 🐟 Улов 🌡 Замеры 🔔 Уведомления 👤 Профиль
  ⚙️ Настройки ✅ Согласия 🛡 Приватность`.
* **Mobile zone selector** — `<optgroup>` с 5 группами архетипов
  (паритет с web/), drop stale codes from localStorage.
* **Лёгкий хедер mobile** — `.app-header` без card-padding, тонкая
  border-bottom, минимальная шапка.

### 18.6 Размеры

| | web/ JS | web/ CSS | mobile JS | mobile CSS | mobile HTML |
|--|---------|----------|-----------|------------|-------------|
| До UI-overhaul | 187 KB | 9 KB | 53 KB | 11 KB | 14 KB |
| После | 190 KB | 13 KB | 60 KB | 13 KB | 14 KB |
| Прирост | +3 KB | +4 KB | +7 KB | +2 KB | 0 |

Прирост незначительный, JS gzip ~61 KB. Рендер визуально богаче без
performance penalty.
