import sys
sys.stdout.reconfigure(encoding='utf-8')

from app import app, db, Expense, Payment
from sqlalchemy import func

with app.app_context():
    print('\n=== Текущее состояние БД ===')
    expenses = Expense.query.all()
    print(f'\nРасходы (всего: {len(expenses)}):')
    for e in expenses:
        print(f'  ID: {e.id}, Category: [{e.category}], Amount: {e.amount}, Source: {e.expense_source}')
    
    payments = Payment.query.all()
    print(f'\nПлатежи (всего: {len(payments)}):')
    for p in payments:
        student_name = p.student.full_name if p.student_id and p.student else 'Нет студента'
        print(f'  ID: {p.id}, Student: {student_name}, Amount: {p.amount_paid}, Type: {p.payment_type}, Notes: {p.notes}')
    
    # Проверим связанные платежи инкассации
    incasso_payments = Payment.query.filter(Payment.notes.like('%Инкассация%')).all()
    print(f'\nСвязанные платежи инкассации: {len(incasso_payments)}')
    for p in incasso_payments:
        print(f'  ID: {p.id}, Amount: {p.amount_paid}, Type: {p.payment_type}, Notes: {p.notes}')
    
    # Проверим баланс
    print('\n=== Расчет баланса ===')
    bank_methods = {
        'paynet', 'oson', 'click', 'payme', 'xazna', 'перечисление', 'transfer', 'uzum', 'uzcard', 'humo', 'card'
    }
    
    total_income = db.session.query(func.sum(Payment.amount_paid)).scalar() or 0
    bank_income = db.session.query(func.sum(Payment.amount_paid)).filter(
        func.lower(func.trim(func.coalesce(Payment.payment_type, 'cash'))).in_(bank_methods)
    ).scalar() or 0
    cash_income = total_income - bank_income
    
    bank_expense = db.session.query(func.sum(Expense.amount)).filter(
        func.lower(func.trim(func.coalesce(Expense.expense_source, ''))) == 'bank'
    ).scalar() or 0
    
    cash_expense = db.session.query(func.sum(Expense.amount)).filter(
        func.lower(func.trim(func.coalesce(Expense.expense_source, ''))) != 'bank'
    ).scalar() or 0
    
    cash_balance = cash_income - cash_expense
    bank_balance = bank_income - bank_expense
    total_balance = cash_balance + bank_balance
    
    print(f'Total income: {total_income}')
    print(f'Cash income: {cash_income}')
    print(f'Bank income: {bank_income}')
    print(f'Cash expense: {cash_expense}')
    print(f'Bank expense: {bank_expense}')
    print(f'\n💰 BALANCES:')
    print(f'Cash balance: {cash_balance}')
    print(f'Bank balance: {bank_balance}')
    print(f'Total balance: {total_balance}')
