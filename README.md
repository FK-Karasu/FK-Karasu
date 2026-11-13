# FK Karasu — CRM футбольной школы

Сайт: https://karasu.uz

Ученики, группы и тарифы, оплаты и баланс, посещаемость через терминалы Hikvision
(Face ID), расходы и инкассация, награды, Telegram-боты для родителей и владельца,
турниры (группы, плей-офф, дисквалификации, картинки для соцсетей).

## Структура

```text
app.py                  Flask-приложение: маршруты и API
telegram_bot.py         бот для родителей
owner_telegram_bot.py   бот владельца
start.sh                запуск в контейнере: gunicorn + оба бота
Dockerfile              образ для сервера
requirements.txt

backend/
  models/models.py      модели SQLAlchemy
  services/             турниры, Face ID, Telegram, карточки лидеров
  utils/, data/         вспомогательный код и справочники
frontend/
  templates/            Jinja-шаблоны страниц
  static/               js, css, картинки, uploads (загруженные фото)
android/                APK для админов: karasu.uz в приложении (сборка: android/build.sh)
bridge/                 мост в клубе: Hikvision → karasu.uz (Node), камера-киоск
models/models/buffalo_s ONNX-модель распознавания лиц (нужна приложению)

scripts/                разовые служебные скрипты, см. scripts/README.md
docs/                   инструкции: деплой, мост Hikvision, Telegram-бот
  archive/              устаревшие инструкции (Railway)
  assets/               исходники картинок
```

## Запуск и деплой

- Деплой: `git push origin main`, сервер собирает сам. Подробно: [docs/DEPLOY.md](docs/DEPLOY.md).
- Локально: `pip install -r requirements.txt`, задать `DATABASE_URL`, `python app.py`.
- Мост и терминалы Hikvision: [docs/HIKVISION_BRIDGE_NOTES.md](docs/HIKVISION_BRIDGE_NOTES.md).
- Telegram-бот: [docs/TELEGRAM_BOT_SETUP.md](docs/TELEGRAM_BOT_SETUP.md).

После правок JS/CSS меняйте `?v=` в подключении файла в шаблоне: Cloudflare кэширует
статику по полному адресу.
