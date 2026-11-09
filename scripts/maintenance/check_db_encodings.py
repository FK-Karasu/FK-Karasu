from app import app, db
from backend.models.models import Student
import numpy as np
import json

with app.app_context():
    students = Student.query.all()
    print(f"Total students in database: {len(students)}")
    
    count_512 = 0
    count_128 = 0
    count_null = 0
    
    for s in students:
        if not s.face_encoding:
            count_null += 1
            continue
            
        try:
            encoding = json.loads(s.face_encoding)
            arr = np.array(encoding)
            if arr.shape[0] == 512:
                count_512 += 1
            elif arr.shape[0] == 128:
                count_128 += 1
            else:
                print(f"Student {s.id} ({s.full_name}) has unknown shape: {arr.shape}")
        except Exception as e:
            print(f"Error parsing encoding for student {s.id}: {e}")
            
    print("-" * 30)
    print(f"InsightFace (512-d): {count_512}")
    print(f"Dlib/Old (128-d): {count_128}")
    print(f"No encoding: {count_null}")
    print("-" * 30)
    
    if count_512 == 1:
        s = Student.query.filter(Student.face_encoding.isnot(None)).first()
        # Double check if only one student is actually used in the engine
        print(f"WARNING: Only ONE student ({s.full_name if s else 'Unknown'}) is loaded for recognition!")
        print("This is why everyone looks like them - they are the only option the AI has.")
