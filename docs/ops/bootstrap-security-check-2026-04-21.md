# Bootstrap/Security Check: fazendaserv (2026-04-21)

## Цель
- Закрыть блок Этапа 1 без WAN: bootstrap/security baseline + автозапуск стека.

## Что проверено
- `docker`: `active`, `enabled`.
- restart policy контейнеров `fishing-forecast`:
  - `api`: `unless-stopped`
  - `db`: `unless-stopped`
  - `redis`: `unless-stopped`
- `GET /v1/ready` на хосте (`127.0.0.1:8000`) возвращает `200`.
- `fail2ban`: `active`, `enabled`.
- `unattended-upgrades`: `active`, `enabled`.
- `ufw`: `active`, `enabled`.
- `sshd_config`:
  - `PermitRootLogin no`
  - `PubkeyAuthentication yes`
  - `PasswordAuthentication no`.

## Статус
- **Autostart readiness:** `PASS` (по systemd + restart policy + local ready).
- **Bootstrap/security baseline:** `PASS`.

## Примечание по применению
- Root hardening успешно применен в интерактивной sudo-сессии.
- Дополнительно обновлен загрузчик `prepare-root-hardening` для auto-fix CRLF (`sed -i 's/\r$//'`) перед запуском скрипта.

## Подготовленный инструмент
- `scripts/verify-bootstrap-security-fazendaserv.ps1`
- `scripts/verify-autostart-fazendaserv.ps1`
- `scripts/harden-host-fazendaserv.ps1` (авто-применение при passwordless sudo, иначе печатает точные команды).
- `scripts/prepare-root-hardening-fazendaserv.ps1` + `scripts/fazendaserv-root-hardening.sh` (однокомандный root-hardening через `sudo bash`).

## Команды (если нужен повторный прогон hardening)
```bash
sudo sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PubkeyAuthentication .*/PubkeyAuthentication yes/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart ssh || sudo systemctl restart sshd
```

После применения:
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\verify-bootstrap-security-fazendaserv.ps1
```
