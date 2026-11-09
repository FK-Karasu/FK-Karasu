# Деплой karasu.uz

С 10.11.2026 сайт работает на домашнем сервере под Coolify (раньше был Railway).

## Как выкатить изменения

```bash
git push origin main
```

GitHub webhook сообщает Coolify о пуше, и Coolify сам собирает образ из `Dockerfile`
и перезапускает контейнер. Проверка: в Coolify (проект **FK Karasu** → **fk-web** →
Deployments) статус `finished`, затем открыть https://karasu.uz/login.

> Cloudflare кэширует статику по полному URL вместе с `?v=`. При каждом изменении JS/CSS
> меняйте `?v=` в шаблоне и не открывайте новый URL, пока деплой не закончился, иначе
> под новым адресом закэшируется старый файл.

## Из чего состоит

| Часть | Где |
|---|---|
| Приложение `fk-web` | Coolify, `Dockerfile`, порт 5000, health check `/login` |
| Запуск внутри контейнера | `start.sh`: gunicorn + клиентский бот + owner-бот |
| База `fk-db` | Coolify, PostgreSQL 17 (база и пользователь `fk`) |
| Загруженные файлы | Docker volume `…-fk_uploads` → `frontend/static/uploads` |
| Вход из интернета | Cloudflare Tunnel → nginx `fk-edge` (порт 3020) → `fk-web:5000` |
| Домены | karasu.uz, www.karasu.uz, event.karasu.uz (Cloudflare, Proxied) |
| Мост в клубе | `karasu-bridge` (Tailscale), код в `bridge/`, шлёт события на https://karasu.uz |

## Переменные окружения

Задаются в Coolify → fk-web → Environment Variables. Основные:
`DATABASE_URL`, `SECRET_KEY`, `APP_URL=https://karasu.uz`, `TELEGRAM_BOT_TOKEN`,
`OWNER_TELEGRAM_BOT_TOKEN`. Для тестовых копий: `RUN_SCHEDULER=0`,
`RUN_CLIENT_TELEGRAM_BOT=0` (чтобы копия не слала уведомления и не перехватывала бота).

## Локальный запуск

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql://...   # без него будет SQLite в database/
python app.py                          # http://localhost:5000
```

На проде PostgreSQL: SQLite не ловит ошибки внешних ключей, поэтому удаление и
миграции проверяйте на копии Postgres.

Старые инструкции под Railway лежат в `docs/archive/` только для истории.
