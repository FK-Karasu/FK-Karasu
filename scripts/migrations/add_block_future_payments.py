import sqlite3
from pathlib import Path

DB_PATH = Path("database/football_school.db")


def main():
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(club_settings)")
    cols = [c[1] for c in cursor.fetchall()]
    print("Existing columns:", cols)

    if "block_future_payments" in cols:
        print("Column block_future_payments already exists")
        conn.close()
        return

    try:
        cursor.execute("ALTER TABLE club_settings ADD COLUMN block_future_payments BOOLEAN DEFAULT 0")
        conn.commit()
        print("✓ Added column block_future_payments")
    except Exception as e:
        print("Error adding column:", e)
        conn.rollback()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
