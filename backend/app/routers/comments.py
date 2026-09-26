from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_optional_user, require_member
from app.database import get_db
from app.models import Comment, CommentLike, Notification, Post, Report, Repost, User
from app.schemas import CommentCreate, CommentOut
from app.utils import abs_url, is_owner, public_nick
from app.storage import log_texto
import re

router = APIRouter()


def _mentions(db, text: str, actor: User, post_id: int):
    names = re.findall(r"@([A-Za-z0-9_]{3,32})", text or "")
    seen = set()
    for raw in names:
        key = raw.lower()
        if key in seen:
            continue
        seen.add(key)
        u = (
            db.query(User)
            .filter((User.username == key) | (User.display_name.ilike(raw)))
            .first()
        )
        if u and u.id != actor.id:
            db.add(
                Notification(
                    user_id=u.id,
                    actor_id=actor.id,
                    post_id=post_id,
                    kind="mention",
                    text=f"@{public_nick(actor)} marcou você",
                )
            )


def _replies_count(db, cid: int) -> int:
    return db.query(Comment).filter(Comment.parent_id == cid).count()


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
        media_url=abs_url(c.media_url or ""),
        parent_id=c.parent_id,
        likes_count=c.likes_count or 0,
        liked=liked,
        featured=featured_id == c.id,
        verified=bool(u and (getattr(u, "is_verified", False) or is_owner(u))),
        replies_count=_replies_count(db, c.id),
        created_at=c.created_at,
    )


@router.get("/{post_id}", response_model=list[CommentOut])
def list_comments(
    post_id: int,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Meme não encontrado")
    rows = db.query(Comment).filter(Comment.post_id == post_id, Comment.parent_id.is_(None)).all()
    rows.sort(key=lambda c: (-(c.likes_count or 0), c.created_at))
    top_id = rows[0].id if post.featured and rows and (rows[0].likes_count or 0) > 0 else None
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
    media = ""
    if body.media_post_id:
        src = db.get(Post, body.media_post_id)
        if not src or src.kind == "video":
            raise HTTPException(400, "Só meme de imagem")
        own = src.user_id == user.id
        rt = db.query(Repost).filter(Repost.user_id == user.id, Repost.post_id == src.id).first()
        if not own and not rt:
            raise HTTPException(403, "Só meme que você postou ou deu RT")
        media = src.media_url
    if not body.text.strip() and not media:
        raise HTTPException(400, "Escreve ou escolhe um meme")
    c = Comment(
        user_id=user.id,
        post_id=post.id,
        parent_id=parent.id if parent else None,
        text=body.text.strip(),
        media_url=media,
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
                text=f"@{public_nick(user)} respondeu você",
            )
        )
    log_texto(user, f"{'resposta' if parent else 'comentario'} post={post.id}: {c.text}")
    _mentions(db, c.text, user, post.id)
    db.commit()
    db.refresh(c)
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


@router.get("/thread/{comment_id}", response_model=list[CommentOut])
def list_replies(
    comment_id: int,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    if not db.get(Comment, comment_id):
        raise HTTPException(404, "Comentário não existe")
    rows = db.query(Comment).filter(Comment.parent_id == comment_id).order_by(Comment.created_at.asc()).all()
    return [_out(db, c, me.id if me else None) for c in rows]


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
    kids = db.query(Comment).filter(Comment.parent_id == c.id).all()
    for k in kids:
        db.query(CommentLike).filter(CommentLike.comment_id == k.id).delete()
        db.delete(k)
    db.query(CommentLike).filter(CommentLike.comment_id == c.id).delete()
    db.query(Report).filter(Report.comment_id == c.id).delete()
    db.delete(c)
    if post:
        post.comments_count = max(0, (post.comments_count or 0) - 1)
    db.commit()
    return {"ok": True}
