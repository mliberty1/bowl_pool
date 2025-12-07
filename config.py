import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'

    # Database configuration
    # On Render, use the persistent volume at /var/data/instance
    # In development, use local sqlite database
    if os.environ.get('DATABASE_URL'):
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    elif os.path.exists('/var/data/instance'):
        # Running on Render with persistent volume
        SQLALCHEMY_DATABASE_URI = 'sqlite:////var/data/instance/bowl_pool.db'
    else:
        # Local development
        SQLALCHEMY_DATABASE_URI = 'sqlite:///bowl_pool.db'

    # Fix for Render's postgres:// vs postgresql://
    if SQLALCHEMY_DATABASE_URI and SQLALCHEMY_DATABASE_URI.startswith('postgres://'):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_TRACK_MODIFICATIONS = False
