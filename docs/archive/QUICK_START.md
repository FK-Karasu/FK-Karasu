# 🚀 Быстрый деплой на Railway - Шпаргалка

## 1️⃣ Подготовка (УЖЕ СДЕЛАНО ✅)

Код уже на GitHub: https://github.com/Alisher1994/FK-QORASUV

## 2️⃣ Деплой на Railway

### Откройте Railway:
👉 https://railway.app

### Создайте проект:
1. **Login with GitHub**
2. **New Project**
3. **Deploy from GitHub repo**
4. Выберите: **FK-QORASUV**

### Добавьте PostgreSQL:
1. Нажмите **"+ New"**
2. **"Database"** → **"Add PostgreSQL"**

### Настройте переменные:
В разделе **Variables** добавьте:

```bash
# Сгенерируйте ключ:
python -c "import secrets; print(secrets.token_hex(32))"

# Добавьте переменные:
SECRET_KEY=<ваш_сгенерированный_ключ>
FLASK_ENV=production
```

### Получите URL:
**Settings** → **Networking** → **Generate Domain**

## 3️⃣ Вход в систему

Откройте ваш Railway URL:
```
Username: admin
Password: admin123
```

## 4️⃣ Что работает автоматически?

✅ **Docker контейнер** с OpenCV и face_recognition  
✅ **PostgreSQL** база данных (не теряет данные!)  
✅ **Веб-камера** для распознавания лиц  
✅ **HTTPS** для работы камеры в браузере  
✅ **Автоинициализация** БД при первом запуске  

## 5️⃣ Создание пользователей

### В Railway Terminal:

```bash
# Финансист
python -c "from backend.models.models import db, User; from app import app, bcrypt; app.app_context().push(); u = User(username='financier', password_hash=bcrypt.generate_password_hash('fin123').decode('utf-8'), role='financier'); db.session.add(u); db.session.commit(); print('OK')"

# Мобильный админ оплат  
python -c "from backend.models.models import db, User; from app import app, bcrypt; app.app_context().push(); u = User(username='payment', password_hash=bcrypt.generate_password_hash('payment123').decode('utf-8'), role='payment_admin'); db.session.add(u); db.session.commit(); print('OK')"

# Учитель (group_id=1)
python -c "from backend.models.models import db, User; from app import app, bcrypt; app.app_context().push(); u = User(username='teacher', password_hash=bcrypt.generate_password_hash('teacher123').decode('utf-8'), role='teacher', group_id=1); db.session.add(u); db.session.commit(); print('OK')"
```

## 6️⃣ Обновление кода

```bash
cd C:\Users\LOQ\Desktop\App\CAM\football_school
git add .
git commit -m "Описание изменений"
git push
```

Railway **автоматически** пересоберет и задеплоит!

## 7️⃣ Мобильные страницы

- **Оплаты**: `https://ваш-url.up.railway.app/mobile-payments`
- **Перекличка**: `https://ваш-url.up.railway.app/teacher-attendance`

## ⚠️ Важно!

### Фото учеников НЕ сохраняются между редеплоями!

**Решение**: Добавьте Railway Volume
1. В Railway: **Settings** → **Volumes**
2. **Add Volume**
3. Mount path: `/app/frontend/static/uploads`

### Камера работает только через HTTPS
Railway автоматически дает HTTPS ✅

## 🐛 Проблемы?

### Логи:
**Railway** → **Deployments** → **View Logs**

### Terminal:
**Railway** → **Deployments** → **View Logs** → **Terminal** (иконка)

### Переинициализация БД:
```bash
python init_db.py
```

## 📚 Полная инструкция

Смотрите: `DEPLOY_RAILWAY.md`

---

**Всё готово! 🎉**

Ваше приложение работает 24/7 с:
- PostgreSQL (данные сохраняются)
- Распознавание лиц (работает)
- Мобильный доступ (работает)
