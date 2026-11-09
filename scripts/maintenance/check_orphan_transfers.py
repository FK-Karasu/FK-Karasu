from app import app, db, Payment, Expense
import re

with app.app_context():
    print("\n=== Все платежи ===\n")
    all_payments = Payment.query.all()
    
    for p in all_payments:
        print(f"ID: {p.id}")
        print(f"  Student: {p.student_id}")
        print(f"  Amount: {p.amount_paid}")
        print(f"  Type: {p.payment_type}")
        print(f"  Notes: {p.notes}")
        
        # Проверяем, является ли это transfer от инкассации
        if p.payment_type == 'transfer' and p.notes and 'Инкассация' in p.notes:
            # Извлекаем ID расхода из notes
            match = re.search(r'Расход #(\d+)', p.notes)
            if match:
                expense_id = int(match.group(1))
                expense = db.session.get(Expense, expense_id)
                if expense:
                    print(f"  ✅ Связанный расход существует: ID {expense_id}, Category: {expense.category}")
                else:
                    print(f"  ❌ ORPHAN! Расход #{expense_id} не найден - это сиротский платеж!")
        else:
            print(f"  Обычный платеж (не инкассация)")
        print()
    
    print(f"\nВсего платежей: {len(all_payments)}")
    
    # Ищем все orphan transfer payments
    print("\n=== Поиск сиротских transfer payments ===\n")
    orphans = []
    for p in all_payments:
        if p.payment_type == 'transfer' and p.notes and 'Инкассация' in p.notes:
            match = re.search(r'Расход #(\d+)', p.notes)
            if match:
                expense_id = int(match.group(1))
                expense = db.session.get(Expense, expense_id)
                if not expense:
                    orphans.append(p)
                    print(f"ORPHAN Payment ID: {p.id}, Amount: {p.amount_paid}, Notes: {p.notes}")
    
    if orphans:
        print(f"\n⚠️ Найдено {len(orphans)} сиротских платежей!")
        print("Эти платежи нужно удалить, так как связанные расходы были удалены.")
    else:
        print("\n✅ Сиротских платежей не найдено")
