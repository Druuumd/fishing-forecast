# Security Review: fazendaserv (2026-04-20)

## Область проверки
- Хост: `fazendaserv` (`192.168.0.250`)
- Сервис: `fishing-forecast` (stage)
- Цель: проверить security baseline Этапа 5 по доступной телеметрии и командам без интерактивного sudo.

## Итог
- **Статус:** `CONDITIONAL PASS`
- **Почему не полный PASS:** не удалось подтвердить часть host-level настроек (`UFW`, `sshd password auth`) без root-доступа.

## Проверенные пункты и результаты

### 1) Контейнеры и сетевой контур fishing-forecast
- `PASS` API-контейнер работает под non-root пользователем (`appuser`).
- `PASS` внутренняя сеть `fishing-forecast_backend` имеет `internal=true`.
- `PASS` только API подключен к внешней bridge-сети (`fishing-forecast_frontend`), `db/redis` в internal-сети.
- `PASS` с клиентской машины:
  - `8000/tcp` доступен;
  - `5432/tcp` и `6379/tcp` закрыты.

### 2) Состояние сервиса
- `PASS` `GET /health` и `GET /ready` успешны.
- `PASS` smoke-проверка API проходит стабильно.

### 3) Host security controls
- `PASS` `fail2ban` активен (`systemctl is-active fail2ban -> active`).
- `PASS` `unattended-upgrades` включен (`systemctl is-enabled unattended-upgrades -> enabled`).
- `UNKNOWN` статус `UFW` (требуется root/sudo без запроса пароля).
- `UNKNOWN` подтверждение `PasswordAuthentication no` в `sshd` (без root не получить надежный `sshd -T`).

## Найденные риски (по приоритету)

### High
- На хосте опубликовано много внешних портов не относящихся к `fishing-forecast` (`8123`, `8080`, `6052`, `3000`, `9090`, `1880`, `1883` и др.).
- Это расширяет поверхность атаки и увеличивает риск lateral movement при компрометации соседнего сервиса.

### Medium
- Нет подтверждения UFW-политики в рамках review (insufficient evidence).
- Нет подтверждения запрета password-auth в SSH (insufficient evidence).

## Рекомендации
1. Под root/sudo подтвердить и сохранить в артефактах:
   - `ufw status verbose`;
   - `sshd -T | egrep 'passwordauthentication|pubkeyauthentication|permitrootlogin'`.
2. Ужесточить ingress на уровне роутера и/или host firewall:
   - оставить открытыми только реально нужные внешние порты;
   - для админских интерфейсов добавить allowlist.
3. Для контейнеров наблюдаемости/IoT рассмотреть:
   - перенос на отдельный хост/VM или отдельный сетевой сегмент;
   - закрытие публичных портов и доступ через VPN/tunnel.

## Доказательства (команды, выполненные в review)
- `docker ps` и `docker compose ps` на `fazendaserv`.
- `ss -ltn` на `fazendaserv`.
- `docker inspect fishing-forecast-api-1 --format '{{.Config.User}}'`.
- `docker network inspect fishing-forecast_backend` и `fishing-forecast_frontend`.
- Локальная проверка: `scripts/verify-network-hardening.ps1 -TargetHost 192.168.0.250`.
- `systemctl is-active fail2ban`, `systemctl is-enabled unattended-upgrades`.

## Резюме для roadmap
- Пункт "Провести security review конфигурации `fazendaserv`" закрыт как выполненный обзор.
- Для полного security baseline требуется закрыть `UNKNOWN` проверки (UFW и SSH password policy) при наличии root/sudo.
