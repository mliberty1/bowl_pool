"""
Unified migration script for deployment.
This runs all necessary migrations to bring the database up to date.
Works with both SQLite and PostgreSQL.
"""
import sys
import os
from app import app
from models import db, RoundStatus

def get_db_connection():
    """Get a raw database connection for running migrations"""
    from sqlalchemy import create_engine
    engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])
    return engine.connect()

def column_exists(conn, table_name, column_name):
    """Check if a column exists in a table"""
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']

    if 'sqlite' in db_uri:
        # SQLite
        result = conn.execute(db.text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result]
        return column_name in columns
    else:
        # PostgreSQL
        result = conn.execute(db.text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name AND column_name = :column_name
        """), {"table_name": table_name, "column_name": column_name})
        return result.fetchone() is not None

def table_exists(conn, table_name):
    """Check if a table exists"""
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']

    if 'sqlite' in db_uri:
        # SQLite
        result = conn.execute(db.text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = :table_name"
        ), {"table_name": table_name})
        return result.fetchone() is not None
    else:
        # PostgreSQL
        result = conn.execute(db.text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_name = :table_name
        """), {"table_name": table_name})
        return result.fetchone() is not None

def migrate_add_round_column():
    """Migration 1: Add 'round' column to bowls table"""
    print("Migration 1: Adding 'round' column to bowls table...")

    with app.app_context():
        conn = get_db_connection()
        trans = conn.begin()

        try:
            if column_exists(conn, 'bowls', 'round'):
                print("  [OK] Column 'round' already exists")
                trans.commit()
                return True

            # Add the column
            print("  [+] Adding 'round' column...")
            if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
                conn.execute(db.text(
                    "ALTER TABLE bowls ADD COLUMN round VARCHAR(50) NOT NULL DEFAULT 'first_round'"
                ))
            else:
                # PostgreSQL
                conn.execute(db.text(
                    "ALTER TABLE bowls ADD COLUMN round VARCHAR(50) NOT NULL DEFAULT 'first_round'"
                ))

            # Update existing rows
            conn.execute(db.text("UPDATE bowls SET round = 'first_round' WHERE round IS NULL OR round = ''"))

            trans.commit()
            print("  [OK] Migration 1 complete")
            return True

        except Exception as e:
            print(f"  [ERROR] Migration 1 failed: {e}")
            trans.rollback()
            return False
        finally:
            conn.close()

def migrate_add_round_status_table():
    """Migration 2: Create round_status table"""
    print("Migration 2: Creating round_status table...")

    with app.app_context():
        conn = get_db_connection()
        trans = conn.begin()

        try:
            if table_exists(conn, 'round_status'):
                print("  [OK] Table 'round_status' already exists")
                trans.commit()
                return True

            # Create the table
            print("  [+] Creating 'round_status' table...")
            if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
                conn.execute(db.text("""
                    CREATE TABLE round_status (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        round_name VARCHAR(50) UNIQUE NOT NULL,
                        is_locked BOOLEAN NOT NULL DEFAULT 0,
                        display_order INTEGER NOT NULL DEFAULT 0
                    )
                """))
            else:
                # PostgreSQL
                conn.execute(db.text("""
                    CREATE TABLE round_status (
                        id SERIAL PRIMARY KEY,
                        round_name VARCHAR(50) UNIQUE NOT NULL,
                        is_locked BOOLEAN NOT NULL DEFAULT FALSE,
                        display_order INTEGER NOT NULL DEFAULT 0
                    )
                """))

            # Get distinct rounds from bowls
            result = conn.execute(db.text("SELECT DISTINCT round FROM bowls ORDER BY round"))
            existing_rounds = [row[0] for row in result]

            # Insert round status records
            round_order = {
                'first_round': 1,
                'quarterfinals': 2,
                'semifinals': 3,
                'championship': 4
            }

            for round_name in existing_rounds:
                is_locked = 1 if round_name == 'first_round' else 0
                order = round_order.get(round_name, 999)

                if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
                    conn.execute(db.text(
                        "INSERT INTO round_status (round_name, is_locked, display_order) VALUES (:name, :locked, :order)"
                    ), {"name": round_name, "locked": is_locked, "order": order})
                else:
                    # PostgreSQL
                    conn.execute(db.text(
                        "INSERT INTO round_status (round_name, is_locked, display_order) VALUES (:name, :locked, :order)"
                    ), {"name": round_name, "locked": is_locked, "order": order})

            trans.commit()
            print(f"  [OK] Migration 2 complete - created {len(existing_rounds)} round status entries")
            return True

        except Exception as e:
            print(f"  [ERROR] Migration 2 failed: {e}")
            trans.rollback()
            return False
        finally:
            conn.close()

def ensure_database_exists():
    """Ensure database file/directory exists and tables are created"""
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']

    if 'sqlite' in db_uri:
        # Extract the database file path
        # sqlite:///relative/path (3 slashes)
        # sqlite:////absolute/path (4 slashes)
        if db_uri.startswith('sqlite:////'):
            # Absolute path - 4 slashes
            db_path = db_uri[10:]  # Remove 'sqlite:///'
        elif db_uri.startswith('sqlite:///'):
            # Relative path - 3 slashes
            db_path = db_uri[10:]  # Remove 'sqlite:///'
        else:
            # Fallback
            db_path = db_uri.replace('sqlite://', '')

        print(f"SQLite database path: {db_path}")

        # Ensure the directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            print(f"Creating database directory: {db_dir}")
            os.makedirs(db_dir, exist_ok=True)

    # Create all tables if they don't exist
    print("Ensuring all tables exist...")
    try:
        db.create_all()
        # Test connection
        db.session.execute(db.text('SELECT 1'))
        db.session.commit()
        print("[OK] Database and base tables ready")
    except Exception as e:
        print(f"[ERROR] Failed to create database: {e}")
        raise

def run_all_migrations():
    """Run all migrations in order"""
    print("="*60)
    print("Running database migrations...")
    print(f"Database: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print("="*60)

    # First, ensure database and base tables exist
    ensure_database_exists()
    print()

    migrations = [
        migrate_add_round_column,
        migrate_add_round_status_table,
    ]

    all_success = True
    for migration in migrations:
        if not migration():
            all_success = False
            print(f"\n[ERROR] Migration failed: {migration.__name__}")
            break

    if all_success:
        print("\n" + "="*60)
        print("[SUCCESS] All migrations completed successfully!")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("[FAILED] Migrations failed - see errors above")
        print("="*60)
        sys.exit(1)

if __name__ == '__main__':
    with app.app_context():
        run_all_migrations()
