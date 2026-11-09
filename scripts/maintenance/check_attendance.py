from app import app, db, Attendance, Student
import sys

with app.app_context():
    print("=== ПРОВЕРКА ПОСЕЩАЕМОСТИ В БАЗЕ ДАННЫХ ===\n")
    
    # Ученик ID=1
    student = Student.query.get(1)
    if student:
        print(f"Ученик: {student.full_name} (ID: {student.id})")
        print(f"Группа ID: {student.group_id}\n")
    
    records = Attendance.query.filter_by(student_id=1).order_by(Attendance.date.desc()).limit(20).all()
    print(f"Найдено записей посещаемости: {len(records)}\n")
    
    for r in records:
        print(f"  ID: {r.id:3d} | Дата: {r.date} | Опоздал: {r.is_late} | Минут опоздания: {r.late_minutes}")
