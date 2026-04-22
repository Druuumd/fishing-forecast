# KVH Forecast Android App

Нативное Android-приложение (WebView shell + mobile MVP assets) находится в директории `android/`.

## Что реализовано
- Android-приложение `ru.kvh.forecast` (Kotlin).
- Встроенный `WebView`, загружающий локальный UI из `mobile-web/`.
- Runtime permissions:
  - геолокация (`ACCESS_FINE_LOCATION`, `ACCESS_COARSE_LOCATION`);
  - уведомления (`POST_NOTIFICATIONS`, Android 13+).
- Native bridge (`AndroidBridge`) для push-теста:
  - `requestNotificationPermission()`
  - `sendTestNotification()`
- Разрешен cleartext-трафик для stage/WAN endpoint (`http://...:8000`).

## Как запустить
1. Открыть в Android Studio папку `android/`.
2. Дождаться Gradle Sync.
3. Запустить `app` на эмуляторе или устройстве (Run).

## Как собрать APK
Через Android Studio:
- `Build` -> `Build Bundle(s) / APK(s)` -> `Build APK(s)`.

## Production release (signed APK/AAB)
1. Создать keystore (один раз):
   - `Build` -> `Generate Signed Bundle / APK`.
2. Скопировать `keystore.properties.example` в `keystore.properties` и заполнить:
   - `storeFile`, `storePassword`, `keyAlias`, `keyPassword`.
3. Положить `.jks` в `android/keystore/` (или указать свой путь в `storeFile`).
4. Убедиться, что `android/keystore.properties` не попал в git (он в `.gitignore`).
5. Собрать release:
   - Android Studio: `Build` -> `Generate Signed Bundle / APK`.

## Versioning
Версия берется из Gradle properties:
- `APP_VERSION_CODE` (int, по умолчанию `1`)
- `APP_VERSION_NAME` (string, по умолчанию `1.0.0`)

Пример в Android Studio/CI:
- `-PAPP_VERSION_CODE=2 -PAPP_VERSION_NAME=1.0.1`

## Источник UI
Ассеты подключены напрямую из `../mobile-web` через `sourceSets.assets.srcDirs`.
Это значит, что изменения в `mobile-web/index.html`, `mobile-web/app.js`, `mobile-web/styles.css` сразу попадают в Android-сборку без дублирования файлов.

## Что добавлено для production UX
- Adaptive app icon (`ic_launcher` / `ic_launcher_round`).
- Splash screen тема (`Theme.KvhForecast.Starting`).
- Network security config для stage/WAN endpoints.
