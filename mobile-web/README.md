# Mobile Web MVP Client

Минимальный mobile-friendly UX клиент для beta:
- login
- forecast
- catch + offline queue
- consent update/read
- DSAR export/delete
- legal links from `/v1/legal/info`
- map + geolocation
- push consent + test notification
- PWA offline cache (service worker)

## Run local

```bash
cd mobile-web
python -m http.server 4173
```

Open:
- `http://localhost:4173`

По умолчанию base URL:
- `http://84.22.146.195:8000`
