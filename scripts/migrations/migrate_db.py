from backend.models.models import db
from app import app

with app.app_context():
    db.drop_all()
    db.create_all()
    print('✅ База данных пересоздана с новыми полями payment_month и payment_year')
