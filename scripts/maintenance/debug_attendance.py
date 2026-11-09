from app import app, db
from backend.models.models import Student, Attendance, get_local_date
import datetime

with app.app_context():
    today = get_local_date()
    print(f"DEBUG: Current Local Date (Tashkent): {today}")
    
    # Check all attendance records
    all_atts = Attendance.query.all()
    print(f"DEBUG: Total attendance records in DB: {len(all_atts)}")
    
    # Check records for today
    today_atts = Attendance.query.filter_by(date=today).all()
    print(f"DEBUG: Records found for date {today}: {len(today_atts)}")
    
    if len(today_atts) == 0 and len(all_atts) > 0:
        print("DEBUG: Sample of latest records dates:")
        for a in all_atts[-5:]:
            print(f"  ID: {a.id}, Student: {a.student_id}, Date: {a.date} (Type: {type(a.date)})")
            
    # Find student by name
    student = Student.query.filter(Student.full_name.like('%Musayev%')).first()
    if student:
        print(f"DEBUG: Found Student: {student.full_name} (ID: {student.id})")
        # Check if they have attendance today
        s_today = Attendance.query.filter_by(student_id=student.id, date=today).first()
        print(f"DEBUG: Attendance for this student TODAY: {'FOUND' if s_today else 'NOT FOUND'}")
        if s_today:
            print(f"  Record ID: {s_today.id}, Check-in: {s_today.check_in} (Type: {type(s_today.check_in)})")
    else:
        print("DEBUG: Student 'Musayev' not found in DB.")
