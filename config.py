import os
import sys
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Secret key validation - require in production
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        # Allow default only in development
        if os.environ.get('FLASK_ENV') == 'production' or not os.environ.get('FLASK_ENV'):
            print("ERROR: SECRET_KEY environment variable must be set in production!", file=sys.stderr)
            # In production (Render), this will be set. If not, fail fast.
            if not os.path.exists('bowl_pool.db'):  # Heuristic: if no local db, assume production
                raise ValueError("SECRET_KEY environment variable is required in production")
        SECRET_KEY = 'dev-secret-key-change-in-production'

    # CSRF Protection
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None  # No time limit for family use

    # Database configuration
    # On Render, use the persistent volume at /var/data/instance
    # In development, use local sqlite database
    if os.environ.get('DATABASE_URL'):
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    else:
        # Local development
        SQLALCHEMY_DATABASE_URI = 'sqlite:///bowl_pool.db'

    # Fix for Render's postgres:// vs postgresql://
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
