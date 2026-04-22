# Release Command Center (2026-04-21)

Единая точка управления финальным MVP релизом на `fazendaserv`.

## Текущий статус
- Backend/infra quality gates: **PASS**.
- WAN endpoint: **PASS** (`84.22.146.195:8000`).
- Mobile UX + beta suite: **PASS**.
- Full web app (React+Vite): **READY FOR DEPLOY**.
- Статус релиза: **CONDITIONAL NO-GO** (до доменного TLS publish).

## Шаг 1. Root hardening (обязательный)
Подготовка (локально):
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\prepare-root-hardening-fazendaserv.ps1
```

Применение (интерактивно на сервере):
```bash
sudo bash /tmp/fazendaserv-root-hardening.sh
```

Проверка (локально):
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\verify-bootstrap-security-fazendaserv.ps1
```

Критерий PASS:
- `ssh_password_auth_no=true`
- `ufw_active=true`
- `fail2ban_active=true`
- `unattended_upgrades_active=true`

Статус:
- Выполнено 2026-04-21 (PASS подтвержден `verify-bootstrap-security-fazendaserv.ps1`).

## Шаг 2. Технические gates
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\run-final-quality-gates-fazendaserv.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run-final-quality-gates-fazendaserv.ps1 -EnableDomainChecks
```

Критерий PASS:
- `overall=PASS`
- все шаги в `PASS` (LAN/WAN/smoke/DQ/ML/DSAR export+delete + domain smoke).

## Шаг 3. Legal финализация (перед public release)
- Прописать production legal значения на `fazendaserv`:
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\set-legal-config-fazendaserv.ps1 -ContactEmail "<email>" -SupportEmail "<email>" -PrivacyUrl "<url>" -TermsUrl "<url>" -DataDeletionUrl "<url>" -CookieTrackingUrl "<url>"
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-fazendaserv.ps1
```
- Проверить legal readiness:
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\verify-legal-readiness-fazendaserv.ps1
```
- Убедиться, что `GET /v1/legal/info` возвращает не-placeholder контакты/URL.

Статус:
- Выполнено 2026-04-21 (`kvh-forecast.ru`, readiness `status=ok`).

## Шаг 4. Web publish checklist
- Сборка frontend:
```bash
cd .\web
npm install
npm run build
```
- Деплой web + api + nginx:
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\deploy-fazendaserv.ps1
```
- Выпуск TLS (Let's Encrypt):
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\setup-domain-tls-fazendaserv.ps1 -Email "admin@kvh-forecast.ru"
```
- Важно: на текущем сервере TLS и доменные роуты обслуживаются через существующий `caddy` (порт `80/443`), а frontend nginx работает на `8081` как upstream.
- Перед smoke проверить DNS:
  - `kvh-forecast.ru -> 84.22.146.195`
  - `api.kvh-forecast.ru -> 84.22.146.195`
- Проверка доменов:
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\smoke-web-domain.ps1
```

Статус:
- Web frontend код готов (`web/`), build проходит.
- Domain smoke сейчас **FAIL** до выпуска сертификатов на сервере.

## Финальное решение GO
Релиз можно перевести в **GO**, когда:
- Шаг 1: PASS
- Шаг 2: PASS
- Legal контакты и URL финализированы
- `https://kvh-forecast.ru` отдает frontend по TLS
- `https://api.kvh-forecast.ru` отдает API по TLS
- Domain smoke: PASS

Decision memo:
- `docs/mvp/release-go-memo-2026-04-21.md`
