import os

class Config:
    # Use SQLite for local development by default
    # This avoids database connection issues during development
    # For production, set DATABASE_URL environment variable
    db_url = os.getenv("DATABASE_URL")
    
    if db_url:
        # Convert old postgres:// to postgresql:// if needed
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = db_url
    else:
        # Default to SQLite for local development
        SQLALCHEMY_DATABASE_URI = "sqlite:///nutrition_app.db"
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
