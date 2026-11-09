import sys
sys.stdout.reconfigure(encoding='utf-8')

from app import app, db, Expense, Payment

with app.app_context():
    exps = Expense.query.all()
    print(f'\nВсего расходов: {len(exps)}')
    for e in exps:
        print(f'ID:{e.id} Category:[{e.category}] Amount:{e.amount} Source:{e.expense_source}')
    
    payments = Payment.query.all()
    print(f'\nВсего платежей: {len(payments)}')
    for p in payments[:10]:
        print(f'ID:{p.id} Amount:{p.amount_paid} Type:{p.payment_type} Student:{p.student_id} Notes:{p.notes[:50] if p.notes else ""}')
