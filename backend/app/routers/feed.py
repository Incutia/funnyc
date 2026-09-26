from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_optional_user
from app.database import get_db
from app.models import Follow, Post, User
from app.utils import post_out

router = APIRouter()


@router.get("/featured")
def featured(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    posts = (
        db.query(Post)
        .filter(Post.featured.is_(True))
        .filter(~Post.tags.ilike("%perfil%"))
        .order_by(Post.created_at.desc())
        .offset(skip)
        .limit(min(limit, 50))
        .all()
    )
    return [post_out(db, p, me.id if me else None) for p in posts]


@router.get("/collective")
def collective(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    posts = (
        db.query(Post)
        .filter(~Post.tags.ilike("%perfil%"))
        .order_by(Post.created_at.desc())
        .offset(skip)
        .limit(min(limit, 50))
        .all()
    )
    return [post_out(db, p, me.id if me else None) for p in posts]


@router.get("/following")
def following_feed(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    if not me:
        return []
    ids = [f.following_id for f in db.query(Follow).filter(Follow.follower_id == me.id).all()]
    if not ids:
        return []
    posts = (
        db.query(Post)
        .filter(Post.user_id.in_(ids))
        .order_by(Post.created_at.desc())
        .offset(skip)
        .limit(min(limit, 50))
        .all()
    )
    return [post_out(db, p, me.id) for p in posts]


@router.get("/explore")
def explore(
    q: str = Query(""),
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    query = db.query(Post)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            (Post.caption.ilike(term)) | (Post.tags.ilike(term))
        )
    posts = query.order_by(Post.smiles_count.desc(), Post.created_at.desc()).offset(skip).limit(min(limit, 50)).all()
    return [post_out(db, p, me.id if me else None) for p in posts]


@router.get("/tags")
def popular_tags(db: Session = Depends(get_db)):
    posts = db.query(Post.tags).all()
    counts: dict[str, int] = {}
    for (raw,) in posts:
        if not raw:
            continue
        for t in raw.split(","):
            t = t.strip().lower()
            if t:
                counts[t] = counts.get(t, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: -x[1])[:20]
    return [{"tag": t, "count": c} for t, c in ranked]
