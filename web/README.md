# KVH Forecast Web

Полноценный web-клиент (React + Vite) для доменной схемы:
- frontend: `https://kvh-forecast.ru`
- API: `https://api.kvh-forecast.ru`

## Quick start

```bash
cd web
npm install
npm run dev
```

Для production сборки:

```bash
npm run build
```

Сборка попадает в `web/dist`.

## Environment

Скопируйте `.env.example` в `.env`:

```bash
VITE_API_BASE_URL=https://api.kvh-forecast.ru
```
