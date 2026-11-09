"""
Скрипт для добавления поля recipient в таблицу cash_transfers
"""
import sqlite3
import os

# Путь к базе данных
db_path = os.path.join(os.path.dirname(__file__), 'database', 'football_school.db')

def add_recipient_column():
    """Добавить поле recipient в таблицу cash_transfers"""
    print(f"Проверяем базу данных: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"❌ База данных не найдена: {db_path}")
        return
    
    print("✓ База данных найдена")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли таблица
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cash_transfers'")
        table_exists = cursor.fetchone()
        
        if not table_exists:
            print("⚠ Таблица cash_transfers не существует. Создаем таблицу...")
            # Создаем таблицу с полной структурой
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cash_transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount FLOAT NOT NULL,
                    recipient VARCHAR(200) NOT NULL,
                    transfer_date TIMESTAMP NOT NULL,
                    notes TEXT,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            ''')
            conn.commit()
            print("✓ Таблица cash_transfers создана!")
        else:
            print("✓ Таблица cash_transfers существует")
            # Проверяем, есть ли уже колонка
            cursor.execute("PRAGMA table_info(cash_transfers)")
            columns = [column[1] for column in cursor.fetchall()]
            print(f"Текущие колонки: {columns}")
            
            if 'recipient' not in columns:
                print("Добавляем колонку recipient...")
                cursor.execute("ALTER TABLE cash_transfers ADD COLUMN recipient VARCHAR(200) DEFAULT ''")
                conn.commit()
                print("✓ Колонка recipient успешно добавлена!")
                
                # Обновить существующие записи (если есть) - установить значение по умолчанию
                cursor.execute("UPDATE cash_transfers SET recipient = 'Не указано' WHERE recipient = '' OR recipient IS NULL")
                conn.commit()
                print("✓ Существующие записи обновлены")
            else:
                print("✓ Колонка recipient уже существует")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()
    print("✅ Миграция завершена!")

if __name__ == '__main__':
    add_recipient_column()
