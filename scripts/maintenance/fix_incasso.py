import sys
sys.stdout.reconfigure(encoding='utf-8')

from app import app, db, Expense, Payment

with app.app_context():
    # Получить первого студента для системных платежей
    from app import Student
    system_student = Student.query.first()
    if not system_student:
        print('ОШИБКА: Нет студентов в базе!')
        sys.exit(1)
    
    print(f'Используем студента ID {system_student.id} ({system_student.full_name}) для системных платежей\n')
    
    # Найти инкассации по кириллице
    expenses = Expense.query.all()
    updated = 0
    
    for expense in expenses:
        cat_lower = (expense.category or '').strip().lower()
        if 'инкас' in cat_lower:
            print(f'\nНайдена инкассация ID {expense.id}, сумма: {expense.amount}')
            print(f'  Старая категория: [{expense.category}]')
            
            # Изменить на Encashment
            expense.category = 'Encashment'
            print(f'  Новая категория: [Encashment]')
            
            # Проверить есть ли связанный payment
            related_payment = Payment.query.filter(
                Payment.notes.like(f'%Инкассация%Расход #{expense.id}%')
            ).first()
            
            if not related_payment:
                print(f'  Создаём связанный платёж transfer')
                payment = Payment(
                    student_id=system_student.id,  # Используем системного студента
                    tariff_id=None,
                    amount_paid=expense.amount,
                    amount_due=0,
                    payment_type='transfer',
                    notes=f'Инкассация (Расход #{expense.id})',
                    lessons_added=0,
                    created_by=expense.created_by
                )
                db.session.add(payment)
            else:
                print(f'  Платёж уже есть: ID {related_payment.id}')
            
            updated += 1
    
    if updated > 0:
        db.session.commit()
        print(f'\n✅ Обновлено {updated} инкассаций')
    else:
        print('\nНет инкассаций для обновления')
