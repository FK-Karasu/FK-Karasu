"""
Скрипт инициализации базы данных для Railway
Создает таблицы и добавляет первого администратора
"""
from app import app, db, bcrypt
from backend.models.models import User, ClubSettings
from datetime import time

def init_database():
    """Инициализация базы данных"""
    with app.app_context():
        print("🔨 Создание таблиц...")
        db.create_all()
        
        # Проверить, есть ли администратор
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            print("👤 Создание администратора...")
            admin = User(
                username='admin',
                password_hash=bcrypt.generate_password_hash('admin123').decode('utf-8'),
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()
            print("✅ Администратор создан: admin / admin123")
        else:
            print("ℹ️  Администратор уже существует")
        
        # Проверить настройки клуба
        settings = ClubSettings.query.first()
        if not settings:
            print("⚙️  Создание настроек клуба...")
            settings = ClubSettings(
                working_days='1,2,3,4,5',  # Пн-Пт
                work_start_time=time(9, 0),
                work_end_time=time(21, 0),
                max_groups_per_slot=4
            )
            db.session.add(settings)
            db.session.commit()
            print("✅ Настройки клуба созданы")
        else:
            print("ℹ️  Настройки клуба уже существуют")
        
        print("\n🎉 База данных успешно инициализирована!")
        print("📍 Войдите как: admin / admin123")

if __name__ == '__main__':
    init_database()
