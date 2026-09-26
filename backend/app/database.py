from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

if settings.DATABASE_URL.startswith("sqlite"):
    raw = settings.DATABASE_URL.replace("sqlite:///", "", 1)
    db_path = Path(raw)
    db_path.parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def migrate():
    stmts = [
        "ALTER TABLE users ADD COLUMN google_id VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN is_anonymous BOOLEAN DEFAULT 0",
        "ALTER TABLE users ADD COLUMN banner_url VARCHAR(500) DEFAULT ''",
        "ALTER TABLE users ADD COLUMN display_name VARCHAR(32) DEFAULT ''",
        "ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0",
        "ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT 0",
        "ALTER TABLE posts ADD COLUMN reposts_count INTEGER DEFAULT 0",
        "ALTER TABLE comments ADD COLUMN parent_id INTEGER",
        "ALTER TABLE comments ADD COLUMN likes_count INTEGER DEFAULT 0",
    ]
    with engine.begin() as conn:
        for sql in stmts:
            try:
                conn.execute(text(sql))
            except Exception:
                pass
        try:
            conn.execute(text("UPDATE users SET is_admin=1, is_verified=1 WHERE lower(email)='c.karlos128@gmail.com'"))
        except Exception:
            pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
