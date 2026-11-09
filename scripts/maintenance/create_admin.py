
import os
import sys
from app import app, db, bcrypt
from backend.models.models import User, Role

def create_admin():
    with app.app_context():
        print("🔍 Проверяем наличие пользователя admin...")
        existing_admin = User.query.filter_by(username='admin').first()
        
        if existing_admin:
            print("✅ Пользователь admin уже существует.")
            # Можно обновить пароль, если нужно, но пока просто сообщим
            return

        print("🛠 Создаем пользователя admin...")
        
        # Получаем роль Администратора (она создается автоматически в app.py)
        admin_role_obj = Role.query.filter_by(name='Администратор').first()
        role_id = admin_role_obj.id if admin_role_obj else None
        
        # Пароль по умолчанию
        password = "admin"
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        new_admin = User(
            username='admin',
            password_hash=hashed_password,
            role='admin',
            role_id=role_id,
            full_name='Super Admin',
            is_active=True
        )
        
        try:
            db.session.add(new_admin)
            db.session.commit()
            print("\n" + "="*40)
            print("🚀 АДМИНИСТРАТОР УСПЕШНО СОЗДАН!")
            print(f"👤 Логин: admin")
            print(f"🔑 Пароль: {password}")
            print("="*40 + "\n")
        except Exception as e:
            print(f"❌ Ошибка при создании: {e}")
            db.session.rollback()

if __name__ == "__main__":
    create_admin()
