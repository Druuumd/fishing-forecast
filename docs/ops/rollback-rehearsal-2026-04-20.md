# Rollback Rehearsal Report (2026-04-20)

## Контекст
- Хост: `fazendaserv` (`192.168.0.250`)
- Сервис: `fishing-forecast` (`api` в docker compose)
- Цель: проверить процедуру отката backend-образа и возврат в стабильное состояние.

## Сценарий
1. Снят baseline image id запущенного `api`.
2. Создан candidate image (`rehearsal-next`) из текущего контейнера.
3. Выполнено переключение `latest` на candidate и `compose up -d api`.
4. Выполнен rollback к baseline image и повторный `compose up -d api`.
5. После репетиции выполнены Gate1 + smoke.

## Результаты
- Baseline image: `sha256:f77512e6697a...`
- Candidate image: `sha256:b71081aa748f...`
- Rollback rehearsal elapsed: `10.1s`.
- Post-check:
  - `GET /health` = `ok`
  - `GET /ready` = `ready` (`db=up`, `redis=up`)
  - smoke-проверка API успешно пройдена.

## Замечания
- Во время переключения образов были краткие `connection reset by peer` на локальных curl-checks (ожидаемо в момент recreate контейнера).
- Итоговое состояние сервиса стабильно и соответствует baseline.
