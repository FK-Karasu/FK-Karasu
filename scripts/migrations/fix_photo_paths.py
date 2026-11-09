"""
Скрипт для исправления путей к фото в базе данных
(заменяет обратные слэши на прямые)
"""
import sqlite3
import os

basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'database', 'football_school.db')

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Получить всех студентов
cursor.execute("SELECT id, photo_path FROM students WHERE photo_path IS NOT NULL")
students = cursor.fetchall()

updated = 0
for student_id, photo_path in students:
    if '\\' in photo_path:
        new_path = photo_path.replace('\\', '/')
        cursor.execute("UPDATE students SET photo_path = ? WHERE id = ?", (new_path, student_id))
        updated += 1
        print(f"Обновлено: {photo_path} -> {new_path}")

conn.commit()
conn.close()

print(f"\nВсего обновлено: {updated} записей")
