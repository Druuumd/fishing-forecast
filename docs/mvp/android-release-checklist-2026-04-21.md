# Android Release Checklist (2026-04-21)

## Build/Config
- [x] Android project создан (`android/`).
- [x] `applicationId` задан: `ru.kvh.forecast`.
- [x] Versioning вынесен в Gradle properties (`APP_VERSION_CODE`, `APP_VERSION_NAME`).
- [x] Release build type включает `minify + shrinkResources`.
- [x] Signing config читает `android/keystore.properties` (если задан).

## UX/Platform
- [x] Launcher icon (adaptive) добавлен.
- [x] Splash screen настроен (`Theme.KvhForecast.Starting`).
- [x] WebView shell загружает локальные assets из `mobile-web`.
- [x] Геолокация runtime permissions подключена.
- [x] Notification runtime permission + test push подключены.

## Network/Security
- [x] `network_security_config` добавлен.
- [x] Cleartext разрешен для stage/WAN endpoints.
- [x] `keystore.properties` и keystore директория исключены из git.

## Release Steps
- [ ] Создать/подключить production keystore (`android/keystore.properties`).
- [ ] Собрать signed APK.
- [ ] Собрать signed AAB.
- [ ] Прогнать smoke на реальном Android-устройстве:
  - login / forecast / catch;
  - consent / DSAR / legal links;
  - map + geolocation;
  - push test.
- [ ] Зафиксировать версию и артефакты в релиз-заметке.
