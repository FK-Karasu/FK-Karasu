"""
Миграция базы данных: добавление групп, адресов и паспортных данных
"""
import sys
import os

# Добавить путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from backend.models.models import Group, Student, Attendance

def migrate_database():
    with app.app_context():
        print("Начало миграции базы данных...")
        
        # Создать все таблицы (новые будут добавлены)
        db.create_all()
        print("✓ Таблицы созданы/обновлены")
        
        # Добавить колонки в существующую таблицу students (если нужно)
        with db.engine.connect() as conn:
            try:
                # Добавить student_number без UNIQUE (добавим индекс позже)
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN student_number VARCHAR(20)
                """))
                print("✓ Добавлена колонка student_number")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    print("  student_number уже существует")
                else:
                    print(f"  Ошибка при добавлении student_number: {e}")
            
            try:
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN group_id INTEGER
                """))
                print("✓ Добавлена колонка group_id")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    print("  group_id уже существует")
            
            try:
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN city VARCHAR(100)
                """))
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN district VARCHAR(100)
                """))
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN street VARCHAR(200)
                """))
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN house_number VARCHAR(50)
                """))
                print("✓ Добавлены колонки адреса")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    print("  Колонки адреса уже существуют")
            
            try:
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN birth_year INTEGER
                """))
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN passport_series VARCHAR(10)
                """))
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN passport_number VARCHAR(20)
                """))
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN passport_issued_by VARCHAR(200)
                """))
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN passport_issue_date DATE
                """))
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN passport_expiry_date DATE
                """))
                print("✓ Добавлены колонки паспортных данных")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    print("  Колонки паспорта уже существуют")
            
            try:
                conn.execute(db.text("""
                    ALTER TABLE students ADD COLUMN club_funded BOOLEAN DEFAULT 0
                """))
                print("✓ Добавлена колонка club_funded")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    print("  club_funded уже существует")
            
            try:
                conn.execute(db.text("""
                    ALTER TABLE attendance ADD COLUMN is_late BOOLEAN DEFAULT 0
                """))
                conn.execute(db.text("""
                    ALTER TABLE attendance ADD COLUMN late_minutes INTEGER DEFAULT 0
                """))
                print("✓ Добавлены колонки опозданий")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    print("  Колонки опозданий уже существуют")
            
            conn.commit()
        
        # Генерировать номера для существующих учеников
        students = Student.query.filter(
            (Student.student_number == None) | (Student.student_number == '')
        ).all()
        
        for idx, student in enumerate(students, start=1):
            student.student_number = f"ST{idx:04d}"
        
        if students:
            db.session.commit()
            print(f"✓ Сгенерированы номера для {len(students)} учеников")
        
        print("\n✅ Миграция завершена успешно!")

if __name__ == '__main__':
    migrate_database()
