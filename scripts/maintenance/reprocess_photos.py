import os
import cv2
import numpy as np
import json
from app import app, db, face_service
from backend.models.models import Student

def reprocess_all_students():
    print("🚀 Начинаем пересчет отпечатков лиц (512-d InsightFace)...")
    
    with app.app_context():
        # Загружаем всех активных студентов
        students = Student.query.all()
        print(f"👥 Всего студентов в базе: {len(students)}")
        
        updated_count = 0
        error_count = 0
        skipped_count = 0
        
        for student in students:
            print(f"--- Обработка: {student.full_name} (ID: {student.id}) ---")
            
            if not student.photo_path:
                print("⚠️ Пропущено: нет пути к фото.")
                skipped_count += 1
                continue
                
            # Путь к фото (может быть относительным или абсолютным)
            photo_path = student.photo_path
            # Если путь начинается с 'frontend/', проверяем его
            full_path = photo_path
            if not os.path.exists(full_path):
                # Пробуем найти в текущей директории или через статику
                candidates = [
                    os.path.join(os.getcwd(), photo_path),
                    os.path.join(os.getcwd(), 'football_school', photo_path),
                    os.path.join(os.getcwd(), 'frontend', 'static', photo_path.replace('static/', ''))
                ]
                found = False
                for cand in candidates:
                    if os.path.exists(cand):
                        full_path = cand
                        found = True
                        break
                if not found:
                    print(f"❌ Ошибка: Файл фото не найден: {photo_path}")
                    error_count += 1
                    continue

            try:
                print(f"📸 Извлечение эмбеддинга из: {full_path}")
                embedding = face_service.extract_embedding(full_path)
                
                if embedding is not None:
                    # Проверяем размерность
                    if embedding.shape[0] == 512:
                        student.set_face_encoding(embedding)
                        db.session.commit()
                        print(f"✅ Успешно обновлено (512-d)!")
                        updated_count += 1
                    else:
                        print(f"⚠️ Получен странный эмбеддинг: {embedding.shape}")
                        error_count += 1
                else:
                    print(f"❌ Не удалось найти лицо на фото.")
                    error_count += 1
            except Exception as e:
                print(f"❌ Критическая ошибка при обработке {student.full_name}: {e}")
                error_count += 1
                db.session.rollback()

        print("\n" + "="*40)
        print(f"📊 ИТОГИ ПЕРЕСЧЕТА:")
        print(f"✅ Обновлено студентов: {updated_count}")
        print(f"⚠️ Пропущено (нет фото): {skipped_count}")
        print(f"❌ Ошибок обработки: {error_count}")
        print("="*40)
        
        if updated_count > 0:
            print("🔄 Перезагружаем кэш ИИ...")
            # reload_face_encodings() - если есть такая функция в app.py
            try:
                from app import reload_face_encodings
                reload_face_encodings()
            except:
                pass
            print("✨ Готово! Теперь все студенты должны распознаваться корректно.")

if __name__ == "__main__":
    reprocess_all_students()
