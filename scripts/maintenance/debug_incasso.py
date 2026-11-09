import sys
sys.stdout.reconfigure(encoding='utf-8')

from app import app, db, Expense
from sqlalchemy import func

with app.app_context():
    expenses = Expense.query.all()
    print(f'\n=== All Expenses (Total: {len(expenses)}) ===')
    for e in expenses:
        print(f'ID: {e.id}, Category: [{e.category}], Amount: {e.amount}, Source: {e.expense_source}')
    
    # Test new SQL query with 'Encashment'
    print('\n=== Testing SQL Query with Encashment ===')
    incasso_filter = func.trim(func.coalesce(Expense.category, '')) == 'Encashment'
    incasso_db = db.session.query(func.sum(Expense.amount)).filter(incasso_filter).scalar() or 0
    print(f'Incasso total from SQL query: {incasso_db}')
    
    # Test balance calculation
    print('\n=== Testing Balance Calculation ===')
    from app import Payment
    
    bank_methods = {
        'paynet', 'oson', 'click', 'payme', 'xazna', 'перечисление', 'transfer', 'uzum', 'uzcard', 'humo', 'card'
    }
    
    total_income = db.session.query(func.sum(Payment.amount_paid)).scalar() or 0
    bank_income = db.session.query(func.sum(Payment.amount_paid)).filter(
        func.lower(func.trim(func.coalesce(Payment.payment_type, 'cash'))).in_(bank_methods)
    ).scalar() or 0
    cash_income = total_income - bank_income
    
    incasso_total = incasso_db
    
    bank_expense = db.session.query(func.sum(Expense.amount)).filter(
        func.lower(func.trim(func.coalesce(Expense.expense_source, ''))) == 'bank',
        ~incasso_filter
    ).scalar() or 0
    
    cash_expense = db.session.query(func.sum(Expense.amount)).filter(
        func.lower(func.trim(func.coalesce(Expense.expense_source, ''))) != 'bank',
        ~incasso_filter
    ).scalar() or 0
    
    cash_expense_total = cash_expense + incasso_total
    bank_income_adjusted = bank_income + incasso_total
    bank_expense_total = bank_expense
    
    cash_balance = cash_income - cash_expense_total
    bank_balance = bank_income_adjusted - bank_expense_total
    total_balance = cash_balance + bank_balance
    
    print(f'Total income: {total_income}')
    print(f'Cash income: {cash_income}')
    print(f'Bank income (original): {bank_income}')
    print(f'Incasso total: {incasso_total}')
    print(f'Bank income (adjusted): {bank_income_adjusted}')
    print(f'Cash expense: {cash_expense}')
    print(f'Cash expense total: {cash_expense_total}')
    print(f'Bank expense: {bank_expense_total}')
    print(f'\n💰 BALANCES:')
    print(f'Cash balance: {cash_balance}')
    print(f'Bank balance: {bank_balance}')
    print(f'Total balance: {total_balance}')
