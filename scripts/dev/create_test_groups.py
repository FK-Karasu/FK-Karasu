"""
Создать тестовые группы
"""
import sys
import os
from datetime import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from backend.models.models import Group

def create_test_groups():
    with app.app_context():
        # Проверить, есть ли уже группы
        if Group.query.count() > 0:
            print("Группы уже существуют")
            return
        
        groups = [
            Group(
                name="Группа 1 (Младшая)",
                schedule_time=time(13, 0),
                late_threshold=15,
                notes="Дети 6-8 лет"
            ),
            Group(
                name="Группа 2 (Средняя)",
                schedule_time=time(15, 0),
                late_threshold=15,
                notes="Дети 9-12 лет"
            ),
            Group(
                name="Группа 3 (Старшая)",
                schedule_time=time(17, 0),
                late_threshold=10,
                notes="Дети 13+ лет"
            )
        ]
        
        for group in groups:
            db.session.add(group)
        
        db.session.commit()
        print(f"✓ Создано {len(groups)} групп")

if __name__ == '__main__':
    create_test_groups()
