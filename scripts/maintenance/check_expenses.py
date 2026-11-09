import sys
from app import app, db, Expense, Payment

with app.app_context():
    # Check ALL expenses with their sources
    print("\n=== ВСЕ РАСХОДЫ ===\n")
    all_expenses = Expense.query.all()
    for e in all_expenses:
        print(f"ID: {e.id}, Source: '{e.expense_source}', Category: '{e.category}', Amount: {e.amount}")
    
    # Check for encashment category variations
    print("\n=== Проверяем инкассации ===\n")
    encashment_like = Expense.query.filter(
        (Expense.category.like('%нкасса%')) | 
        (Expense.category.like('%ncashment%'))
    ).all()
    
    print(f"Найдено инкассаций: {len(encashment_like)}")
    for e in encashment_like:
        print(f"ID: {e.id}, Source: '{e.expense_source}', Category: '{e.category}', Amount: {e.amount}")
        # Check if transfer payment exists
        transfer = Payment.query.filter(
            Payment.notes.like(f'%Расход #{e.id}%')
        ).first()
        print(f"  Связанный transfer payment: {'Да, ID={transfer.id}' if transfer else 'Нет'}")
        print()
    
    # Check all payments
    print("\n=== Все платежи ===\n")
    all_payments = Payment.query.all()
    print(f"Всего платежей: {len(all_payments)}")
    for p in all_payments:
        print(f"ID: {p.id}, Student: {p.student_id}, Amount: {p.amount_paid}, Type: {p.payment_type}, Notes: {p.notes}")
