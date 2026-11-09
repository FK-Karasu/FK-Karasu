"""
Скрипт для создания пользователя с ролью payment_admin
"""
from backend.models.models import db, User
from app import app, bcrypt

def create_payment_admin():
    with app.app_context():
        # Проверить, существует ли пользователь
        existing_user = User.query.filter_by(username='payment').first()
        if existing_user:
            print('❌ Пользователь "payment" уже существует')
            return
        
        # Создать нового пользователя
        password = 'payment123'  # Можно изменить на свой пароль
        password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        
        new_user = User(
            username='payment',
            password_hash=password_hash,
            role='payment_admin'
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        print('✅ Создан пользователь для мобильных оплат:')
        print(f'   Логин: payment')
        print(f'   Пароль: {password}')
        print(f'   Роль: payment_admin')
        print()
        print('🔗 Ссылка для входа: http://127.0.0.1:5000/login')

if __name__ == '__main__':
    create_payment_admin()
