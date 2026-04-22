# WAN Endpoint Validation (2026-04-21)

## Контур
- Роутер: TP-Link Archer AX55.
- WAN endpoint: `84.22.146.195:8000`.
- Backend host: `fazendaserv` (`192.168.0.250:8000`).
- NAT rule: `TCP/8000 -> 192.168.0.250:8000`.

## Проверки
- TCP reachability:
  - `Test-NetConnection 84.22.146.195 -Port 8000` -> `TcpTestSucceeded=True`.
- HTTP health:
  - `curl http://84.22.146.195:8000/health` -> `{"status":"ok"}`.
- HTTP ready:
  - `curl http://84.22.146.195:8000/ready` -> `{"status":"ready","env":"stage","db":"up","redis":"up"}`.

## Итог
- WAN доступ к API подтвержден.
- Пункты roadmap по внешнему endpoint и Gate 1 извне можно считать закрытыми.
