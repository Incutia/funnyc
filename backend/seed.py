from app.database import Base, SessionLocal, engine
from app.models import Comment, Collect, Post, Smile, User

Base.metadata.create_all(bind=engine)


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
            print(f"Removeu {len(gone)} memes de exemplo.")
        if not db.query(User).filter(User.username == "funnyc").first():
            from app.auth import hash_password

            bot = User(
                username="funnyc",
                email="hello@funnyc.app",
                password_hash=hash_password("funnyc123"),
                bio="Conta oficial.",
                is_anonymous=False,
            )
            db.add(bot)
            db.commit()
        print("Seed ok. Destaques vazios até alguém postar.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
