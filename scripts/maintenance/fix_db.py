from app import app
from backend.models.models import db, Student
import json

def fix_database():
    print("🚑 Начинаем лечение базы данных...")
    with app.app_context():
        students = Student.query.all()
        fixed_count = 0
        
        for student in students:
            if student.face_encoding:
                try:
                    # Пытаемся прочитать как JSON
                    json.loads(student.face_encoding)
                except Exception as e:
                    print(f"⚠️ Найдена ошибка у ученика ID {student.id} ({student.full_name}): {e}")
                    # Очищаем битое поле. Фото на диске осталось, так что 
                    # при следующем обновлении фото оно пересоздастся правильно.
                    # Либо можно попробовать пересоздать прямо сейчас, если фото есть
                    student.face_encoding = None 
                    fixed_count += 1
        
        if fixed_count > 0:
            db.session.commit()
            print(f"✅ Исправлено учеников: {fixed_count}")
        else:
            print("👌 База данных в порядке, ошибок не найдено.")

if __name__ == "__main__":
    fix_database()
