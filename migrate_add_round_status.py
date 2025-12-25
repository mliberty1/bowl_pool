"""
Migration script to add 'round_status' table.
Run this ONCE after updating models.py
"""
import sqlite3
import os

DB_PATH = r'C:\repos\personal\bowl_pool\instance\bowl_pool.db'

def migrate():
    """Add round_status table and populate with existing rounds"""
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='round_status'")
        if cursor.fetchone():
            print("Table 'round_status' already exists. Migration not needed.")
            return True

        # Create the round_status table
        print("Creating 'round_status' table...")
        cursor.execute("""
            CREATE TABLE round_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_name VARCHAR(50) UNIQUE NOT NULL,
                is_locked BOOLEAN NOT NULL DEFAULT 0,
                display_order INTEGER NOT NULL DEFAULT 0
            )
        """)

        # Get distinct rounds from bowls table
        cursor.execute("SELECT DISTINCT round FROM bowls ORDER BY round")
        existing_rounds = [row[0] for row in cursor.fetchall()]

        # Insert round status records for each existing round
        # First round is locked by default, others are unlocked
        round_order = {
            'first_round': 1,
            'quarterfinals': 2,
            'semifinals': 3,
            'championship': 4
        }

        for round_name in existing_rounds:
            is_locked = 1 if round_name == 'first_round' else 0
            order = round_order.get(round_name, 999)
            cursor.execute(
                "INSERT INTO round_status (round_name, is_locked, display_order) VALUES (?, ?, ?)",
                (round_name, is_locked, order)
            )

        conn.commit()
        print(f"Migration successful! Created round_status table with {len(existing_rounds)} round(s).")

        # Verify
        cursor.execute("SELECT round_name, is_locked FROM round_status ORDER BY display_order")
        rounds = cursor.fetchall()
        print("\nRound status:")
        for round_name, is_locked in rounds:
            status = "LOCKED" if is_locked else "UNLOCKED"
            print(f"  - {round_name}: {status}")

        return True

    except sqlite3.Error as e:
        print(f"Error during migration: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()

if __name__ == '__main__':
    print("=== Bowl Pool Database Migration: Add Round Status ===")
    print("This will create a 'round_status' table to manage which rounds are open for picks.")
    print(f"Database: {DB_PATH}\n")

    response = input("Continue? (yes/no): ")
    if response.lower() == 'yes':
        success = migrate()
        if success:
            print("\nMigration complete! You can now manage round status via the admin interface.")
        else:
            print("\nMigration failed. Please check the error messages above.")
    else:
        print("Migration cancelled.")
