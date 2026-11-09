from app import app, db
from backend.models.models import ClubSettings
import json

with app.app_context():
    settings = ClubSettings.query.first()
    if settings and settings.expense_categories:
        try:
            categories = json.loads(settings.expense_categories)
            print(f"Текущие категории: {categories}")
            
            # Убираем Encashment и Инкасация из настроек
            original_count = len(categories)
            categories = [cat for cat in categories if cat not in ['Encashment', 'Инкасация']]
            
            if len(categories) < original_count:
                settings.expense_categories = json.dumps(categories)
                db.session.commit()
                print(f"\n✅ Удалено {original_count - len(categories)} технических категорий")
                print(f"Новые категории: {categories}")
            else:
                print("\n✅ Технические категории не найдены")
        except Exception as e:
            print(f"Ошибка: {e}")
    else:
        print("Настройки не содержат категории")
