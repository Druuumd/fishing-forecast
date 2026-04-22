# Fazendaserv Bootstrap (192.168.0.250)

## Сетевой контур
- Используется статический внешний IP маршрутизатора (WAN).
- Внешний доступ к API: `WAN IP роутера` -> `NAT/port-forward` -> `fazendaserv:8000`.
- Локальный адрес сервера (`192.168.0.250`) не используется как публичный endpoint для клиентов из интернета.

## Минимальная подготовка сервера
- Установить Docker Engine + Docker Compose plugin.
- Создать директорию проекта: `/home/drumd/fishing-forecast` (или другой путь, доступный пользователю деплоя).
- Убедиться, что пользователь деплоя имеет доступ к docker.
- Настроить на роутере правило port-forward для `TCP/8000` на `192.168.0.250:8000`.

## Security hardening (Phase 1)
- Включить UFW:
  - разрешить `22/tcp`;
  - разрешить `8000/tcp` только для нужных источников (или временно для теста);
  - закрыть все остальное по умолчанию.
- Установить и включить `fail2ban`.
- Отключить SSH password auth, оставить key-only.
- Включить автообновления безопасности.

## Команды проверки после деплоя
На локальной машине:
```bash
powershell -ExecutionPolicy Bypass -File .\scripts\verify-gate1.ps1
curl http://<WAN_STATIC_IP>:8000/health
curl http://<WAN_STATIC_IP>:8000/ready
```

На сервере:
```bash
cd /home/drumd/fishing-forecast
docker compose -f docker-compose.yml -f docker-compose.stage.yml ps
docker logs --tail 50 fishing-forecast-api-1
```
