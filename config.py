import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / '.env')

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-dev-insecure-secret-key-change-in-production-12345')
    
    # Priority:
    # 1. DATABASE_URL environment variable (e.g. mysql+pymysql://user:pass@localhost:3306/finance_db)
    # 2. SQLite local database (convenient for zero-configuration startup)
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', 'root')
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = os.environ.get('DB_PORT', '3306')
    DB_NAME = os.environ.get('DB_NAME', 'finance_db')
    
    DEFAULT_SQLITE_URI = f"sqlite:///{BASE_DIR / 'finance_db.sqlite3'}"
    
    # If MYSQL_URL is explicitly set or USE_MYSQL is true
    USE_MYSQL = os.environ.get('USE_MYSQL', 'false').lower() in ('true', '1', 'yes')
    if USE_MYSQL:
        SQLALCHEMY_DATABASE_URI = os.environ.get(
            'DATABASE_URL', 
            f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )
    else:
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', DEFAULT_SQLITE_URI)
        
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() in ('true', '1', 'yes')
    UPLOAD_FOLDER = BASE_DIR / 'uploads'
