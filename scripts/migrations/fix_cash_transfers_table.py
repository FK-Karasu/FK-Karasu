"""
Скрипт для исправления таблицы cash_transfers
Удаляет старую колонку transferred_to и создает правильную структуру
"""
import sqlite3
from pathlib import Path

DB_PATH = Path("database/football_school.db")

def fix_cash_transfers_table():
    if not DB_PATH.exists():
        print(f"База данных не найдена: {DB_PATH}")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Проверяем, существует ли таблица
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cash_transfers'")
        if not cursor.fetchone():
            print("Таблица cash_transfers не существует. Она будет создана автоматически при первом использовании.")
            return
        
        # Проверяем существующие колонки
        cursor.execute("PRAGMA table_info(cash_transfers)")
        columns = {col[1]: col for col in cursor.fetchall()}
        
        print("Существующие колонки:", list(columns.keys()))
        
        # Если есть transferred_to, нужно пересоздать таблицу
        if 'transferred_to' in columns:
            print("\nОбнаружена старая колонка transferred_to. Пересоздаем таблицу...")
            
            # Сохраняем данные
            cursor.execute("SELECT * FROM cash_transfers")
            old_data = cursor.fetchall()
            print(f"Найдено {len(old_data)} записей для сохранения")
            
            # Создаем временную таблицу с правильной структурой
            cursor.execute("""
                CREATE TABLE cash_transfers_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount FLOAT NOT NULL,
                    recipient VARCHAR(200) NOT NULL,
                    transfer_date TIMESTAMP NOT NULL,
                    notes TEXT,
                    created_by INTEGER,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP,
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            """)
            
            # Копируем данные из старой таблицы
            if old_data:
                # Определяем индексы колонок в старой таблице
                old_cols = list(columns.keys())
                
                for row in old_data:
                    row_dict = dict(zip(old_cols, row))
                    
                    # Извлекаем данные
                    transfer_id = row_dict.get('id')
                    amount = row_dict.get('amount', 0)
                    recipient = row_dict.get('transferred_to') or row_dict.get('recipient') or 'Не указано'
                    transfer_date = row_dict.get('transfer_date') or row_dict.get('transfer_date')
                    notes = row_dict.get('notes', '')
                    created_by = row_dict.get('created_by')
                    created_at = row_dict.get('created_at')
                    updated_at = row_dict.get('updated_at')
                    
                    cursor.execute("""
                        INSERT INTO cash_transfers_new 
                        (amount, recipient, transfer_date, notes, created_by, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (amount, recipient, transfer_date, notes, created_by, created_at, updated_at))
            
            # Удаляем старую таблицу
            cursor.execute("DROP TABLE cash_transfers")
            
            # Переименовываем новую таблицу
            cursor.execute("ALTER TABLE cash_transfers_new RENAME TO cash_transfers")
            
            conn.commit()
            print("✓ Таблица cash_transfers успешно пересоздана")
            
        else:
            # Просто проверяем и добавляем недостающие колонки
            print("\nПроверяем структуру таблицы...")
            
            required_cols = {
                'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
                'amount': 'FLOAT NOT NULL',
                'recipient': 'VARCHAR(200)',
                'transfer_date': 'TIMESTAMP',
                'notes': 'TEXT',
                'created_by': 'INTEGER',
                'created_at': 'TIMESTAMP',
                'updated_at': 'TIMESTAMP'
            }
            
            for col_name, col_type in required_cols.items():
                if col_name not in columns:
                    if col_name == 'id':
                        continue  # id уже есть
                    try:
                        cursor.execute(f"ALTER TABLE cash_transfers ADD COLUMN {col_name} {col_type}")
                        print(f"✓ Добавлена колонка {col_name}")
                    except sqlite3.OperationalError as e:
                        if "duplicate column" in str(e).lower():
                            print(f"  Колонка {col_name} уже существует")
                        else:
                            raise
            
            # Заполняем recipient, если он NULL
            cursor.execute("UPDATE cash_transfers SET recipient = 'Не указано' WHERE recipient IS NULL OR recipient = ''")
            conn.commit()
            print("✓ Данные обновлены")
            
    except Exception as e:
        conn.rollback()
        print(f"Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_cash_transfers_table()







