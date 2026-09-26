from pathlib import Path
import struct
import zlib

from app.auth import hash_password
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Collect, Comment, Post, Smile, User

Base.metadata.create_all(bind=engine)


def _png(path: Path, r: int, g: int, b: int, w: int = 640, h: int = 640) -> None:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b""
    for _ in range(h):
        raw += b"\x00" + bytes([r, g, b]) * w
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def run():
    db = SessionLocal()
    try:
        gone = db.query(Post).filter(Post.media_url.like("%picsum.photos%")).all()
        for p in gone:
            db.query(Smile).filter(Smile.post_id == p.id).delete()
            db.query(Collect).filter(Collect.post_id == p.id).delete()
            db.query(Comment).filter(Comment.post_id == p.id).delete()
            db.delete(p)
        if gone:
            db.commit()

        bot = db.query(User).filter(User.username == "funnyc").first()
        if not bot:
            bot = User(
                username="funnyc",
                email="hello@funnyc.app",
                password_hash=hash_password("funnyc123"),
                bio="Conta oficial do Funnyc.",
                display_name="Funnyc",
                is_anonymous=False,
                is_verified=True,
                is_admin=False,
            )
            db.add(bot)
            db.commit()
            db.refresh(bot)
        else:
            bot.display_name = bot.display_name or "Funnyc"
            bot.is_verified = True
            db.commit()

        print("Seed ok. Sem conta oficial no feed.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
