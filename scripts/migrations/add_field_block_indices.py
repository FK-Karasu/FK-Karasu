import sqlite3
from pathlib import Path

DB_PATH = Path("database/football_school.db")

def main():
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(groups)")
    cols = [c[1] for c in cursor.fetchall()]
    print("Existing columns:", cols)

    if "field_block_indices" in cols:
        print("Column field_block_indices already exists")
        conn.close()
        return

    try:
        cursor.execute("ALTER TABLE groups ADD COLUMN field_block_indices TEXT")
        conn.commit()
        print("✓ Added column field_block_indices")
    except Exception as e:
        print(f"Error adding column: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
