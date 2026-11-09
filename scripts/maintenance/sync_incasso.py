import sys
sys.stdout.reconfigure(encoding='utf-8')

from app import app, db, Expense, Payment

with app.app_context():
    # Найти все инкассации без связанных payments
    encashments = Expense.query.filter(Expense.category == 'Encashment').all()
    print(f'\n=== Найдено инкассаций: {len(encashments)} ===')
    
    for expense in encashments:
        print(f'\nИнкассация ID {expense.id}, сумма: {expense.amount}')
        
        # Проверить есть ли связанный payment
        related_payment = Payment.query.filter(
            Payment.notes.like(f'Инкассация (Расход #{expense.id})')
        ).first()
        
        if related_payment:
            print(f'  ✓ Уже есть связанный платёж ID {related_payment.id}')
        else:
            print(f'  ✗ Нет связанного платежа - создаём!')
            payment = Payment(
                student_id=None,
                tariff_id=None,
                amount_paid=expense.amount,
                amount_due=0,
                payment_type='transfer',
                notes=f'Инкассация (Расход #{expense.id})',
                lessons_added=0,
                created_by=expense.created_by
            )
            db.session.add(payment)
    
    db.session.commit()
    print('\n✅ Все инкассации синхронизированы с платежами!')
