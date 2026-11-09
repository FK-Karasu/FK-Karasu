import sqlite3
from datetime import datetime

DB_PATH = 'database/football_school.db'

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Создание таблицы тарифов и обновление схемы...")
    
    try:
        # 1. Создать таблицу tariffs
        print("\n1. Создание таблицы tariffs...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tariffs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL UNIQUE,
                lessons_count INTEGER NOT NULL,
                price FLOAT NOT NULL,
                description TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("✓ Таблица tariffs создана")
        
        # 2. Добавить поле schedule_days в groups
        print("\n2. Добавление поля schedule_days в groups...")
        try:
            cursor.execute('ALTER TABLE groups ADD COLUMN schedule_days VARCHAR(50)')
            print("✓ Поле schedule_days добавлено")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e):
                print("⚠ Поле schedule_days уже существует")
            else:
                raise
        
        # 3. Создать новую таблицу payments с обновленной схемой
        print("\n3. Обновление таблицы payments...")
        
        # Проверить существующие столбцы
        cursor.execute("PRAGMA table_info(payments)")
        existing_columns = {col[1] for col in cursor.fetchall()}
        
        needs_migration = 'tariff_id' not in existing_columns
        
        if needs_migration:
            # Сохранить старые данные
            cursor.execute('ALTER TABLE payments RENAME TO payments_old')
            
            # Создать новую таблицу
            cursor.execute('''
                CREATE TABLE payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL,
                    tariff_id INTEGER,
                    amount_paid FLOAT NOT NULL,
                    amount_due FLOAT DEFAULT 0,
                    lessons_added INTEGER NOT NULL,
                    is_full_payment BOOLEAN DEFAULT 1,
                    payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tariff_name VARCHAR(100),
                    notes TEXT,
                    created_by INTEGER,
                    FOREIGN KEY (student_id) REFERENCES students(id),
                    FOREIGN KEY (tariff_id) REFERENCES tariffs(id),
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            ''')
            
            # Перенести данные
            cursor.execute('''
                INSERT INTO payments (
                    id, student_id, amount_paid, lessons_added, 
                    payment_date, tariff_name, notes, created_by
                )
                SELECT 
                    id, student_id, amount, lessons_added,
                    payment_date, tariff_name, notes, created_by
                FROM payments_old
            ''')
            
            # Удалить старую таблицу
            cursor.execute('DROP TABLE payments_old')
            print("✓ Таблица payments обновлена")
        else:
            print("⚠ Таблица payments уже обновлена")
        
        # 4. Добавить тестовые тарифы
        print("\n4. Добавление тестовых тарифов...")
        test_tariffs = [
            ("Тариф 4 занятия", 4, 200000, "Базовый тариф на 4 занятия"),
            ("Тариф 8 занятий", 8, 360000, "Стандартный тариф на 8 занятий"),
            ("Тариф 12 занятий", 12, 500000, "Расширенный тариф на 12 занятий"),
            ("Разовое занятие", 1, 60000, "Разовое посещение")
        ]
        
        for name, lessons, price, desc in test_tariffs:
            cursor.execute('''
                INSERT OR IGNORE INTO tariffs (name, lessons_count, price, description)
                VALUES (?, ?, ?, ?)
            ''', (name, lessons, price, desc))
        
        print("✓ Тестовые тарифы добавлены")
        
        conn.commit()
        print("\n✅ Миграция завершена успешно!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Ошибка миграции: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
