from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

url = settings.DATABASE_URL
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql+psycopg2://", 1)
elif url.startswith("postgresql://") and "+psycopg2" not in url:
    url = url.replace("postgresql://", "postgresql+psycopg2://", 1)

if url.startswith("sqlite"):
    raw = url.replace("sqlite:///", "", 1)
    Path(raw).parent.mkdir(parents=True, exist_ok=True)

connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
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
        "ALTER TABLE users ADD COLUMN banned BOOLEAN DEFAULT 0",
        "ALTER TABLE messages ADD COLUMN media_url VARCHAR(400) DEFAULT ''",
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
