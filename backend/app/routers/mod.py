from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_staff
from app.database import get_db
from app.models import Comment, Post, Report, User
from app.utils import abs_url, public_nick

router = APIRouter()


@router.get("/reports")
def reports(me: User = Depends(require_staff), db: Session = Depends(get_db)):
    rows = db.query(Report).order_by(Report.created_at.desc()).limit(120).all()
    out = []
    for r in rows:
        post = db.get(Post, r.post_id) if r.post_id else None
        com = db.get(Comment, r.comment_id) if r.comment_id else None
        who = db.get(User, r.user_id)
        out.append(
            {
                "id": r.id,
                "reason": r.reason or "denúncia",
                "username": public_nick(who) if who else "",
                "post_id": r.post_id,
                "comment_id": r.comment_id,
                "text": (com.text if com else (post.caption if post else "")),
                "media_url": abs_url(post.media_url) if post else "",
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
        )
    return out


@router.get("/users")
def staff_users(q: str = "", me: User = Depends(require_staff), db: Session = Depends(get_db)):
    query = db.query(User).filter(User.is_anonymous.is_(False))
    if q.strip():
        t = f"%{q.strip()}%"
        query = query.filter((User.username.ilike(t)) | (User.email.ilike(t)))
    rows = query.order_by(User.created_at.desc()).limit(40).all()
    return [
        {
            "username": u.username,
            "email": u.email,
            "banned": bool(getattr(u, "banned", False)),
            "verified": bool(u.is_verified),
            "moderator": bool(getattr(u, "is_moderator", False)),
        }
        for u in rows
    ]
