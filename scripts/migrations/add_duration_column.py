"""
Скрипт для добавления поля duration_minutes в таблицу groups
"""
import sqlite3
import os

# Путь к базе данных
db_path = os.path.join(os.path.dirname(__file__), 'database', 'football_school.db')

def add_duration_column():
    """Добавить поле duration_minutes в таблицу groups"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Проверяем, есть ли уже колонка
        cursor.execute("PRAGMA table_info(groups)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'duration_minutes' not in columns:
            print("Добавляем колонку duration_minutes...")
            cursor.execute("ALTER TABLE groups ADD COLUMN duration_minutes INTEGER DEFAULT 60")
            conn.commit()
            print("✓ Колонка duration_minutes успешно добавлена!")
        else:
            print("Колонка duration_minutes уже существует")
            
    except Exception as e:
        print(f"Ошибка: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    add_duration_column()
