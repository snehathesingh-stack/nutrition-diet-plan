import os

class Config:
    db_url = os.getenv("DATABASE_URL")
    
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI = db_url
    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///nutrition_app.db"
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_timeout": 10,
        "pool_recycle": 300,
        "connect_args": {"connect_timeout": 5}
    }