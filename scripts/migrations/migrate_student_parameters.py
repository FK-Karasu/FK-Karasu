"""
Миграция: добавление полей параметров ученика (рост, вес, размеры)
"""
import sqlite3
import os

DB_PATH = 'database/football_school.db'

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"База данных не найдена: {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Добавление полей параметров ученика...")
    
    try:
        # Проверить существующие колонки
        cursor.execute("PRAGMA table_info(students)")
        existing_columns = {col[1] for col in cursor.fetchall()}
        
        # Добавить колонки, если их нет
        columns_to_add = [
            ('height', 'INTEGER'),
            ('weight', 'REAL'),
            ('jersey_size', 'VARCHAR(20)'),
            ('shorts_size', 'VARCHAR(20)'),
            ('boots_size', 'VARCHAR(20)'),
            ('equipment_notes', 'TEXT')
        ]
        
        for col_name, col_type in columns_to_add:
            if col_name not in existing_columns:
                try:
                    cursor.execute(f'ALTER TABLE students ADD COLUMN {col_name} {col_type}')
                    print(f"✓ Добавлена колонка: {col_name}")
                except sqlite3.OperationalError as e:
                    if "duplicate column" in str(e).lower():
                        print(f"⚠ Колонка {col_name} уже существует")
                    else:
                        raise
            else:
                print(f"ℹ Колонка {col_name} уже существует")
        
        conn.commit()
        print("\n✅ Миграция успешно выполнена!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Ошибка миграции: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()





