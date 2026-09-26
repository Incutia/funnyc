from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_optional_user, require_member
from app.database import get_db
from app.models import Comment, CommentLike, Notification, Post, Report, User
from app.schemas import CommentCreate, CommentOut
from app.utils import abs_url, is_owner, public_nick
from app.storage import log_texto

router = APIRouter()


def _out(db, c: Comment, me_id: int | None, featured_id: int | None = None) -> CommentOut:
    u = db.get(User, c.user_id)
    liked = False
    if me_id:
        liked = (
            db.query(CommentLike).filter(CommentLike.user_id == me_id, CommentLike.comment_id == c.id).first()
            is not None
        )
    return CommentOut(
        id=c.id,
        user_id=c.user_id,
        username=public_nick(u) if u else "deleted",
        avatar_url=abs_url(u.avatar_url or "") if u else "",
        text=c.text,
        parent_id=c.parent_id,
        likes_count=c.likes_count or 0,
        liked=liked,
        featured=featured_id == c.id,
        verified=bool(u and (getattr(u, "is_verified", False) or is_owner(u))),
        created_at=c.created_at,
    )


@router.get("/{post_id}", response_model=list[CommentOut])
def list_comments(
    post_id: int,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    if not db.get(Post, post_id):
        raise HTTPException(404, "Meme não encontrado")
    rows = db.query(Comment).filter(Comment.post_id == post_id).all()
    rows.sort(key=lambda c: (-(c.likes_count or 0), c.created_at))
    top_id = rows[0].id if rows and (rows[0].likes_count or 0) > 0 else None
    return [_out(db, c, me.id if me else None, top_id) for c in rows]


@router.post("/{post_id}", response_model=CommentOut)
def add_comment(
    post_id: int,
    body: CommentCreate,
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Meme não encontrado")
    parent = None
    if body.parent_id:
        parent = db.get(Comment, body.parent_id)
    c = Comment(
        user_id=user.id,
        post_id=post.id,
        parent_id=parent.id if parent else None,
        text=body.text.strip(),
    )
    db.add(c)
    post.comments_count += 1
    target = parent.user_id if parent else post.user_id
    if target != user.id:
        db.add(
            Notification(
                user_id=target,
                actor_id=user.id,
                post_id=post.id,
                kind="reply",
                text=f"@{user.username} respondeu você",
            )
        )
    db.commit()
    db.refresh(c)
    log_texto(user, f"{'resposta' if parent else 'comentario'} post={post.id}: {c.text}")
    return _out(db, c, user.id)


@router.post("/like/{comment_id}")
def like_comment(
    comment_id: int,
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    c = db.get(Comment, comment_id)
    if not c:
        raise HTTPException(404, "Comentário não existe")
    existing = db.query(CommentLike).filter(CommentLike.user_id == user.id, CommentLike.comment_id == c.id).first()
    if existing:
        db.delete(existing)
        c.likes_count = max(0, (c.likes_count or 0) - 1)
    else:
        db.add(CommentLike(user_id=user.id, comment_id=c.id))
        c.likes_count = (c.likes_count or 0) + 1
    db.commit()
    db.refresh(c)
    return _out(db, c, user.id)


@router.post("/report/{comment_id}")
def report_comment(
    comment_id: int,
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    if not db.get(Comment, comment_id):
        raise HTTPException(404, "Comentário não existe")
    db.add(Report(user_id=user.id, comment_id=comment_id, reason="comentario"))
    db.commit()
    return {"ok": True}


@router.delete("/{comment_id}")
def delete_comment(
    comment_id: int,
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    c = db.get(Comment, comment_id)
    if not c:
        raise HTTPException(404, "Comentário não existe")
    owner = getattr(user, "is_admin", False) or (user.email or "").lower() == "c.karlos128@gmail.com"
    if c.user_id != user.id and not owner:
        raise HTTPException(403, "Só o autor ou o dono apaga")
    post = db.get(Post, c.post_id)
    db.query(CommentLike).filter(CommentLike.comment_id == c.id).delete()
    db.delete(c)
    if post:
        post.comments_count = max(0, (post.comments_count or 0) - 1)
    db.commit()
    return {"ok": True}
