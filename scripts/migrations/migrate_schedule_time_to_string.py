"""
Миграция: изменить тип колонки schedule_time с TIME на VARCHAR
чтобы поддерживать как простое время "HH:MM", так и JSON с разными временами для разных дней
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from backend.models.models import Group
from datetime import time

def migrate():
    with app.app_context():
        print("🔄 Начало миграции schedule_time...")
        
        try:
            # Получаем все группы
            groups = Group.query.all()
            print(f"📊 Найдено {len(groups)} групп")
            
            # Сохраняем текущие значения
            group_times = {}
            for group in groups:
                if isinstance(group.schedule_time, time):
                    # Конвертируем time в строку
                    group_times[group.id] = group.schedule_time.strftime('%H:%M')
                else:
                    # Уже строка
                    group_times[group.id] = str(group.schedule_time)
            
            print("💾 Сохранены текущие значения времени")
            
            # Изменяем тип колонки через SQL
            with db.engine.begin() as conn:
                print("🔧 Изменение типа колонки...")
                
                # Для SQLite нужно пересоздать таблицу
                conn.execute(db.text("""
                    CREATE TABLE groups_new (
                        id INTEGER PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        schedule_time VARCHAR(500) NOT NULL,
                        duration_minutes INTEGER DEFAULT 60,
                        schedule_days VARCHAR(50),
                        late_threshold INTEGER DEFAULT 15,
                        max_students INTEGER,
                        field_blocks INTEGER DEFAULT 1,
                        field_block_indices TEXT,
                        notes TEXT,
                        created_at TIMESTAMP
                    )
                """))
                
                # Копируем данные
                conn.execute(db.text("""
                    INSERT INTO groups_new 
                    SELECT id, name, 
                           CASE 
                               WHEN schedule_time IS NULL THEN '09:00'
                               ELSE strftime('%H:%M', schedule_time)
                           END as schedule_time,
                           duration_minutes, schedule_days, late_threshold, 
                           max_students, field_blocks, field_block_indices, 
                           notes, created_at
                    FROM groups
                """))
                
                # Удаляем старую таблицу
                conn.execute(db.text("DROP TABLE groups"))
                
                # Переименовываем новую таблицу
                conn.execute(db.text("ALTER TABLE groups_new RENAME TO groups"))
                
            print("✅ Тип колонки изменен на VARCHAR(500)")
            
            # Восстанавливаем значения
            for group_id, time_str in group_times.items():
                group = db.session.get(Group, group_id)
                if group:
                    group.schedule_time = time_str
            
            db.session.commit()
            print("✅ Миграция завершена успешно!")
            
        except Exception as e:
            print(f"❌ Ошибка при миграции: {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate()
