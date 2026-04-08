import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-fixmycity'
    
    # Path to SQLite DB
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixmycity.db')
    
    # Upload folder
    UPLOAD_FOLDER = os.path.join('static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # 16 MB max upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
