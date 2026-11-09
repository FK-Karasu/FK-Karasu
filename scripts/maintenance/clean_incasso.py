import sys
sys.stdout.reconfigure(encoding='utf-8')

from app import app, db, Expense, Payment

with app.app_context():
    # Удалить все расходы инкассации
    encashment_expenses = Expense.query.filter(Expense.category == 'Encashment').all()
    print(f'Найдено расходов Encashment: {len(encashment_expenses)}')
    for e in encashment_expenses:
        print(f'Удаляю расход ID {e.id}')
        db.session.delete(e)
    
    db.session.commit()
    print('Готово! Теперь можно добавить новую инкассацию через UI')
