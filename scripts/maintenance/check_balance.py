from app import app, db, Payment, Expense
from sqlalchemy import func

with app.app_context():
    # Check payments
    total_income = db.session.query(func.sum(Payment.amount_paid)).scalar() or 0
    
    bank_methods = {
        'paynet', 'oson', 'click', 'payme', 'xazna', 'перечисление', 'transfer', 
        'uzum', 'uzcard', 'humo', 'card'
    }
    
    bank_income = db.session.query(func.sum(Payment.amount_paid)).filter(
        func.lower(func.trim(func.coalesce(Payment.payment_type, 'cash'))).in_(bank_methods)
    ).scalar() or 0
    
    cash_income = total_income - bank_income
    
    print(f"Total income: {total_income}")
    print(f"Bank income: {bank_income}")
    print(f"Cash income: {cash_income}")
    print()
    
    # Check expenses
    bank_expense = db.session.query(func.sum(Expense.amount)).filter(
        func.lower(func.trim(func.coalesce(Expense.expense_source, ''))) == 'bank'
    ).scalar() or 0
    
    cash_expense = db.session.query(func.sum(Expense.amount)).filter(
        func.lower(func.trim(func.coalesce(Expense.expense_source, ''))) != 'bank'
    ).scalar() or 0
    
    print(f"Bank expense: {bank_expense}")
    print(f"Cash expense: {cash_expense}")
    print()
    
    # Calculate balances
    cash_balance = cash_income - cash_expense
    bank_balance = bank_income - bank_expense
    total_balance = cash_balance + bank_balance
    
    print(f"Cash balance: {cash_balance}")
    print(f"Bank balance: {bank_balance}")
    print(f"Total balance: {total_balance}")
