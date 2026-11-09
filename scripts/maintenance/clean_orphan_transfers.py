from app import app, db, Payment, Expense
import re

with app.app_context():
    print("\n=== Удаление сиротских transfer payments ===\n")
    
    orphans = []
    all_payments = Payment.query.all()
    
    for p in all_payments:
        if p.payment_type == 'transfer' and p.notes and 'Инкассация' in p.notes:
            match = re.search(r'Расход #(\d+)', p.notes)
            if match:
                expense_id = int(match.group(1))
                expense = db.session.get(Expense, expense_id)
                if not expense:
                    orphans.append(p)
                    print(f"Найден сиротский платеж:")
                    print(f"  ID: {p.id}")
                    print(f"  Amount: {p.amount_paid}")
                    print(f"  Notes: {p.notes}")
                    print(f"  Расход #{expense_id} не существует")
    
    if orphans:
        print(f"\nВсего найдено сиротских платежей: {len(orphans)}")
        print("Удаляем...")
        
        for p in orphans:
            print(f"  Удаляем Payment ID {p.id} (Amount: {p.amount_paid})")
            db.session.delete(p)
        
        db.session.commit()
        print(f"\n✅ Успешно удалено {len(orphans)} сиротских платежей!")
        
        # Проверяем результат
        remaining = Payment.query.all()
        print(f"\nОставшиеся платежи: {len(remaining)}")
        for p in remaining:
            print(f"  ID: {p.id}, Amount: {p.amount_paid}, Type: {p.payment_type}, Notes: {p.notes}")
    else:
        print("Сиротских платежей не найдено")
