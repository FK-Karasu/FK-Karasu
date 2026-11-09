#!/usr/bin/env python3
"""
Скрипт для инициализации типов карточек в базе данных
"""
import sys
import os

# Добавить путь к проекту
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import app
from backend.models.models import db, CardType

def init_card_types():
    """Инициализировать типы карточек"""
    with app.app_context():
        # Проверить, существуют ли уже типы карточек
        existing = CardType.query.first()
        if existing:
            print("Типы карточек уже существуют в базе данных")
            return
        
        # Создать типы карточек
        card_types = [
            CardType(name='Желтая', color='yellow', description='Предупреждение'),
            CardType(name='Красная', color='red', description='Удаление с поля'),
            CardType(name='Оранжевая', color='orange', description='Серьезное нарушение'),
            CardType(name='Синяя', color='blue', description='Замечание'),
            CardType(name='Зеленая', color='green', description='Положительное поведение')
        ]
        
        for card_type in card_types:
            db.session.add(card_type)
        
        db.session.commit()
        print("✓ Типы карточек успешно созданы:")
        for ct in card_types:
            print(f"  - {ct.name} ({ct.color})")

if __name__ == '__main__':
    init_card_types()





