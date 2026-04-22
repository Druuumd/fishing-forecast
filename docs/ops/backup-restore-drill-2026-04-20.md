# Backup/Restore Drill Report (2026-04-20)

## Контекст
- Хост: `fazendaserv` (`192.168.0.250`)
- БД: PostgreSQL в compose-сервисе `db`
- Backup path: `/home/drumd/fishing-forecast/backups/db`

## Выполненные шаги
1. Запущен backup:
   - `scripts/backup-db-fazendaserv.ps1`
   - создан файл: `forecast_20260420_235416.dump`
2. Запущен restore drill:
   - `scripts/restore-drill-fazendaserv.ps1`
   - источник: `forecast_20260420_235416.dump`
   - восстановление в временный контейнер drill.
3. Валидация:
   - таблица `catch_records` восстановлена;
   - количество записей: `31`.
4. Настроен ежедневный cron backup:
   - `scripts/install-backup-cron-fazendaserv.ps1`
   - расписание: `03:00` ежедневно;
   - retention: `30` дней.

## Фактические показатели
- Restore drill elapsed: `4.7s` (по выводу скрипта).
- Фактический `RTO` для drill: менее `1` минуты.
- Фактический `RPO` (по возрасту последнего backup): в пределах `24` часов.

## Вывод
- Backup и restore drill для MVP работают.
- Текущие показатели укладываются в целевые ориентиры runbook (`RPO <= 24h`, `RTO <= 60m`).
