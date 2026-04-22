# Release GO Memo (2026-04-21)

## Executive Decision
- **Текущий вердикт:** `CONDITIONAL NO-GO`.
- **Причина:** web release контур реализован, но доменный TLS publish еще не подтвержден smoke-проверкой.

## What Is Ready (Evidence-backed)
- Backend API контракт (`v1`) стабилен и проверен.
- Data layer / migrations / cache / auth / anti-abuse / audit logging — внедрены.
- WAN endpoint на `84.22.146.195:8000` подтвержден.
- Host security baseline (включая `PasswordAuthentication no`) подтвержден.
- Final technical quality gates — `PASS`.
- Legal contacts/URLs на `kvh-forecast.ru` применены и проверены (`/v1/legal/info`).
- Mobile UX реализован + Android app shell (`android/`) готов под APK сборку.
- Full web app (`web/`, React + Vite) собран и готов к публикации.

Ключевые артефакты:
- `docs/mvp/release-gate-status-2026-04-21.md`
- `docs/mvp/final-quality-gates-2026-04-21.md`
- `docs/mvp/release-command-center-2026-04-21.md`
- `docs/mvp/mobile-handoff-pack-2026-04-21.md`
- `docs/mvp/mobile-beta-test-cases-2026-04-21.md`

## Open Blockers to Full GO
1. DNS cutover:
   - `kvh-forecast.ru` должен указывать на `84.22.146.195` (сейчас указывает на другой внешний IP);
   - `api.kvh-forecast.ru` должен быть создан как `A -> 84.22.146.195` (сейчас NXDOMAIN).
2. После DNS обновления domain smoke должен пройти:
   - `powershell -ExecutionPolicy Bypass -File .\scripts\smoke-web-domain.ps1`

## Residual Risk Snapshot
- **High:** недоступность публичного web для пользователей до DNS cutover.
- **Medium:** время DNS propagation и возможная задержка авто-выпуска TLS на новом endpoint.
- **Low:** инфраструктурные и backend риски (контролируются текущими gates/runbooks).

## Decision Criteria for GO
Перевод в **GO** разрешен только при выполнении всех условий:
- Web build в `web/dist` собран и задеплоен. **PASS**
- TLS для `kvh-forecast.ru` и `api.kvh-forecast.ru` выпущен. **PENDING**
- Domain smoke (`smoke-web-domain.ps1`) проходит. **PENDING**
- Нет открытых P0/P1. **PASS**
- Финальный подтверждающий прогон:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run-final-quality-gates-fazendaserv.ps1`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\run-final-quality-gates-fazendaserv.ps1 -EnableDomainChecks`
  - `powershell -ExecutionPolicy Bypass -File .\scripts\verify-legal-readiness-fazendaserv.ps1`

## Sign-off Fields
- Product owner: `PENDING (после domain TLS PASS)`
- Backend lead: `READY`
- Ops/SRE: `READY`
- Mobile lead: `READY`
- Legal/privacy owner: `READY`
