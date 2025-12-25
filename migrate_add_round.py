"""
Migration script to add 'round' column to bowls table.
Run this ONCE after updating models.py
"""
import sqlite3
import os

DB_PATH = r'C:\repos\personal\bowl_pool\instance\bowl_pool.db'

def migrate():
    """Add round column to bowls table"""
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(bowls)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'round' in columns:
            print("Column 'round' already exists. Migration not needed.")
            return True

        # Add the column with default value
        print("Adding 'round' column to bowls table...")
        cursor.execute("ALTER TABLE bowls ADD COLUMN round VARCHAR(50) NOT NULL DEFAULT 'first_round'")

        # Update all existing bowls to 'first_round'
        cursor.execute("UPDATE bowls SET round = 'first_round'")

        conn.commit()
        print(f"Migration successful! Updated {cursor.rowcount} existing bowl(s).")

        # Verify
        cursor.execute("SELECT COUNT(*) FROM bowls WHERE round = 'first_round'")
        count = cursor.fetchone()[0]
        print(f"Verified: {count} bowl(s) now have round = 'first_round'")

        return True

    except sqlite3.Error as e:
        print(f"Error during migration: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()

if __name__ == '__main__':
    print("=== Bowl Pool Database Migration ===")
    print("This will add a 'round' column to the bowls table.")
    print(f"Database: {DB_PATH}\n")

    response = input("Continue? (yes/no): ")
    if response.lower() == 'yes':
        success = migrate()
        if success:
            print("\nMigration complete! You can now run the application.")
        else:
            print("\nMigration failed. Please check the error messages above.")
    else:
        print("Migration cancelled.")
