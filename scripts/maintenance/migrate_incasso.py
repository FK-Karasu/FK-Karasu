import sys
sys.stdout.reconfigure(encoding='utf-8')

from app import app, db, Expense

with app.app_context():
    expenses = Expense.query.all()
    updated = 0
    for e in expenses:
        cat = (e.category or '').strip().lower()
        if 'инкас' in cat:
            print(f'Обновляю расход ID {e.id}: {e.category} -> Encashment')
            e.category = 'Encashment'
            updated += 1
    
    if updated > 0:
        db.session.commit()
        print(f'\nУспешно обновлено {updated} записей')
    else:
        print('Нет записей для обновления')
