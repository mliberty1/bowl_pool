"""
Database initialization script.
Run this to create all tables in the database.
"""
from app import app
from models import db


def init_database():
    """Initialize the database by creating all tables"""
    with app.app_context():
        # Create all tables
        db.create_all()
        print("Database tables created successfully!")


if __name__ == '__main__':
    init_database()
