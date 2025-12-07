"""
Database initialization script.
Run this to create all tables in the database.
"""
from app import app
from models import db
import os


def init_database():
    """Initialize the database by creating all tables"""
    with app.app_context():
        # Print configuration info
        print(f"Current working directory: {os.getcwd()}")
        print(f"Database URL: {app.config['SQLALCHEMY_DATABASE_URI']}")

        # Create all tables
        try:
            db.create_all()
            # Force a connection to ensure the database file is created
            db.session.execute(db.text('SELECT 1'))
            db.session.commit()
            print("Database tables created successfully!")
        except Exception as e:
            print(f"Error creating database: {e}")
            raise

        # For SQLite, show the database file location
        db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        if db_uri.startswith('sqlite:///'):
            db_path = db_uri.replace('sqlite:///', '')

            # Check both the specified path and the instance folder
            full_path = os.path.abspath(db_path)
            instance_path = os.path.join(app.instance_path, os.path.basename(db_path))

            print(f"Expected SQLite database location: {full_path}")
            if os.path.exists(full_path):
                print(f"Database file exists: YES")
                size = os.path.getsize(full_path)
                print(f"Database file size: {size} bytes")
            elif os.path.exists(instance_path):
                print(f"Database file NOT found at expected location")
                print(f"But found in instance folder: {instance_path}")
                size = os.path.getsize(instance_path)
                print(f"Database file size: {size} bytes")
            else:
                print(f"Database file exists: NO (this might indicate an error)")


if __name__ == '__main__':
    init_database()
