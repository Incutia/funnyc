from datetime import datetime, timedelta
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_optional_user
from app.config import settings
from app.database import get_db
from app.models import Follow, Notification, Post, Repost, User
from app.utils import post_out, public_nick, user_out

router = APIRouter()
SNAP = Path(settings.UPLOAD_DIR).resolve().parent / "collective.json"


def _dump(db, posts, me):
    return [post_out(db, p, me.id if me else None) for p in posts]


@router.get("/featured")
def featured(
    skip: int = 0,
    limit: int = 30,
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
    return _dump(db, posts, me)


@router.get("/following")
def following_feed(
    skip: int = 0,
    limit: int = 30,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    if not me:
        return []
    ids = [f.following_id for f in db.query(Follow).filter(Follow.follower_id == me.id).all()]
    if not ids:
        return []
    own = db.query(Post).filter(Post.user_id.in_(ids)).all()
    rts = db.query(Repost).filter(Repost.user_id.in_(ids)).all()
    extra_ids = {r.post_id for r in rts}
    extra = db.query(Post).filter(Post.id.in_(extra_ids)).all() if extra_ids else []
    seen = set()
    posts = []
    for p in sorted(list(own) + list(extra), key=lambda x: x.created_at or datetime.min, reverse=True):
        if p.id in seen:
            continue
        seen.add(p.id)
        posts.append(p)
    return _dump(db, posts[skip : skip + min(limit, 50)], me)


def _score(p: Post) -> int:
    return (p.smiles_count or 0) * 3 + (p.comments_count or 0) * 2 + (getattr(p, "views_count", 0) or 0)


def _refresh_collective(db: Session) -> list[int]:
    posts = db.query(Post).filter(~Post.tags.ilike("%perfil%")).all()
    ranked = sorted(posts, key=_score, reverse=True)[:30]
    ids = [p.id for p in ranked]
    SNAP.parent.mkdir(parents=True, exist_ok=True)
    SNAP.write_text(json.dumps({"at": datetime.utcnow().isoformat(), "ids": ids}), encoding="utf-8")
    if ids:
        top = db.get(Post, ids[0])
        author = db.get(User, top.user_id) if top else None
        text = f"Novo destaque: meme de {public_nick(author) if author else 'funnyc'}"
        people = db.query(User).filter(User.is_anonymous.is_(False)).all()
        for u in people:
            db.add(Notification(user_id=u.id, actor_id=top.user_id if top else None, post_id=ids[0], kind="destaque", text=text))
        db.commit()
    return ids


@router.get("/collective")
def collective(
    skip: int = 0,
    limit: int = 30,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    ids = []
    stale = True
    if SNAP.exists():
        try:
            data = json.loads(SNAP.read_text(encoding="utf-8"))
            at = datetime.fromisoformat(data.get("at", "2000-01-01"))
            ids = list(data.get("ids") or [])
            stale = datetime.utcnow() - at >= timedelta(hours=3) or not ids
        except Exception:
            stale = True
    if stale:
        ids = _refresh_collective(db)
    posts = db.query(Post).filter(Post.id.in_(ids)).all() if ids else []
    order = {i: n for n, i in enumerate(ids)}
    posts.sort(key=lambda p: order.get(p.id, 999))
    return _dump(db, posts[skip : skip + min(limit, 50)], me)


@router.get("/collective/clock")
def collective_clock():
    next_at = datetime.utcnow() + timedelta(hours=3)
    if SNAP.exists():
        try:
            data = json.loads(SNAP.read_text(encoding="utf-8"))
            at = datetime.fromisoformat(data.get("at", "2000-01-01"))
            next_at = at + timedelta(hours=3)
        except Exception:
            pass
    left = max(0, int((next_at - datetime.utcnow()).total_seconds()))
    h, rem = divmod(left, 3600)
    m, s = divmod(rem, 60)
    return {"seconds": left, "label": f"{h:02d}:{m:02d}:{s:02d}"}


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
        query = query.filter((Post.caption.ilike(term)) | (Post.tags.ilike(term)))
    posts = query.order_by(Post.smiles_count.desc(), Post.created_at.desc()).offset(skip).limit(min(limit, 50)).all()
    return _dump(db, posts, me)


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


@router.get("/people")
def search_people(q: str = Query(""), db: Session = Depends(get_db)):
    term = q.strip().lstrip("@").lower()
    query = db.query(User).filter(User.is_anonymous.is_(False))
    if term:
        query = query.filter((User.username.ilike(f"%{term}%")) | (User.display_name.ilike(f"%{term}%")))
    rows = query.order_by(User.created_at.desc()).limit(30).all()
    return [user_out(db, u) for u in rows]
