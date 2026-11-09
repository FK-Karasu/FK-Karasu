"""
Миграция: добавление поля blacklist_reason
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def migrate_blacklist():
    with app.app_context():
        print("Добавление поля blacklist_reason...")
        
        with db.engine.connect() as conn:
            try:
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN blacklist_reason TEXT
                """))
                conn.commit()
                print("✓ Поле blacklist_reason добавлено")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    print("  blacklist_reason уже существует")
                else:
                    print(f"  Ошибка: {e}")
        
        print("✅ Миграция завершена!")

if __name__ == '__main__':
    migrate_blacklist()
