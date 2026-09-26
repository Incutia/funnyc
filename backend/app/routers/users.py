from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session
from pathlib import Path
import uuid

from app.auth import get_current_user, get_optional_user, require_member, require_owner
from app.config import settings
from app.database import get_db
from app.models import Collect, Comment, Follow, Notification, Post, Repost, Smile, User
from app.schemas import ProfileUpdate
from app.utils import post_out, public_nick, user_out
from app.storage import save_into, write_conta

router = APIRouter()


def find_user(db: Session, key: str) -> User | None:
    k = key.strip()
    user = db.query(User).filter(User.username == k.lower()).first()
    if user:
        return user
    return db.query(User).filter(User.display_name == k).first()


@router.patch("/me")
def update_me(
    body: ProfileUpdate,
    me: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    if body.username:
        nick = body.username.strip()
        if len(nick) < 3:
            raise HTTPException(400, "Nick mínimo 3 letras")
        me.display_name = nick[:32]
        slug = "".join(ch for ch in nick.lower() if ch.isalnum() or ch == "_")[:24]
        if len(slug) >= 3:
            taken = db.query(User).filter(User.username == slug, User.id != me.id).first()
            if not taken:
                me.username = slug
    if body.bio is not None:
        me.bio = body.bio[:200]
    if body.avatar_url is not None:
        me.avatar_url = body.avatar_url
    if body.banner_url is not None:
        me.banner_url = body.banner_url
    db.commit()
    db.refresh(me)
    write_conta(me)
    return user_out(db, me)


@router.post("/me/setup")
def setup_me(
    nick: str = Form(""),
    bio: str = Form(""),
    avatar: UploadFile | None = File(None),
    banner: UploadFile | None = File(None),
    me: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    name = nick.strip()
    if len(name) >= 2:
        me.display_name = name[:32]
        slug = "".join(ch for ch in name.lower() if ch.isalnum() or ch == "_")[:24]
        if len(slug) >= 2:
            taken = db.query(User).filter(User.username == slug, User.id != me.id).first()
            if not taken:
                me.username = slug
    me.bio = bio.strip()[:200]
    if avatar is not None and avatar.filename:
        me.avatar_url = _save_pic(avatar, "av", me)
    if banner is not None and banner.filename:
        me.banner_url = _save_pic(banner, "bn", me)
    db.commit()
    db.refresh(me)
    write_conta(me)
    return user_out(db, me)


def _save_pic(file: UploadFile, prefix: str, user: User | None = None) -> str:
    suffix = Path(file.filename or "pic.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        raise HTTPException(400, "Use jpg, png, gif ou webp")
    data = file.file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(400, "Imagem máx 8MB")
    name = f"{prefix}-{uuid.uuid4().hex}{suffix}"
    if user is not None:
        return save_into(user, "perfil", name, data)
    dest_dir = Path(settings.UPLOAD_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / name).write_bytes(data)
    return f"/media/{name}"


@router.post("/me/avatar")
def set_avatar(file: UploadFile = File(...), me: User = Depends(require_member), db: Session = Depends(get_db)):
    me.avatar_url = _save_pic(file, "av", me)
    db.commit()
    db.refresh(me)
    return user_out(db, me)


@router.post("/me/banner")
def set_banner(file: UploadFile = File(...), me: User = Depends(require_member), db: Session = Depends(get_db)):
    me.banner_url = _save_pic(file, "bn", me)
    db.commit()
    db.refresh(me)
    return user_out(db, me)


def _posts_from(db, rows, me_id):
    out = []
    for r in rows:
        p = db.get(Post, r.post_id)
        if p:
            out.append(post_out(db, p, me_id))
    return out


@router.get("/me/likes")
def my_likes(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Smile).filter(Smile.user_id == me.id).order_by(Smile.created_at.desc()).all()
    return _posts_from(db, rows, me.id)


@router.get("/me/reposts")
def my_reposts(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Repost).filter(Repost.user_id == me.id).order_by(Repost.created_at.desc()).all()
    return _posts_from(db, rows, me.id)


@router.get("/me/memes")
def my_memes(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    own = db.query(Post).filter(Post.user_id == me.id, Post.kind == "image").order_by(Post.created_at.desc()).all()
    rts = db.query(Repost).filter(Repost.user_id == me.id).order_by(Repost.created_at.desc()).all()
    seen = set()
    out = []
    for p in own:
        seen.add(p.id)
        out.append(post_out(db, p, me.id))
    for r in rts:
        p = db.get(Post, r.post_id)
        if p and p.id not in seen and p.kind == "image":
            seen.add(p.id)
            out.append(post_out(db, p, me.id))
    return out


@router.get("/me/replies")
def my_replies(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    notes = (
        db.query(Notification)
        .filter(Notification.user_id == me.id)
        .order_by(Notification.created_at.desc())
        .limit(80)
        .all()
    )
    mine = (
        db.query(Comment)
        .filter(Comment.user_id == me.id)
        .order_by(Comment.created_at.desc())
        .limit(80)
        .all()
    )
    items = []
    for n in notes:
        actor = db.get(User, n.actor_id) if n.actor_id else None
        items.append(
            {
                "kind": "notification",
                "text": n.text,
                "username": public_nick(actor) if actor else "",
                "post_id": n.post_id,
                "created_at": n.created_at.isoformat() if n.created_at else "",
            }
        )
    for c in mine:
        items.append(
            {
                "kind": "comment",
                "text": c.text,
                "username": me.username,
                "post_id": c.post_id,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            }
        )
    return items


@router.get("/{username}/reposts")
def public_reposts(
    username: str,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    user = find_user(db, username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    rows = db.query(Repost).filter(Repost.user_id == user.id).order_by(Repost.created_at.desc()).all()
    return _posts_from(db, rows, me.id if me else None)


@router.get("/{username}/likes")
def public_likes(
    username: str,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = find_user(db, username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    if user.id != me.id:
        raise HTTPException(403, "Likes são privados")
    rows = db.query(Smile).filter(Smile.user_id == user.id).order_by(Smile.created_at.desc()).all()
    return _posts_from(db, rows, me.id)


@router.get("/{username}")
def profile(
    username: str,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    user = find_user(db, username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    data = user_out(db, user).model_dump()
    data["is_me"] = bool(me and me.id == user.id)
    data["is_anonymous"] = bool(user.is_anonymous)
    data["is_following"] = False
    if me and me.id != user.id:
        data["is_following"] = (
            db.query(Follow)
            .filter(Follow.follower_id == me.id, Follow.following_id == user.id)
            .first()
            is not None
        )
    posts = db.query(Post).filter(Post.user_id == user.id).order_by(Post.created_at.desc()).all()
    data["posts"] = [post_out(db, p, me.id if me else None) for p in posts]
    if data["is_me"]:
        likes = db.query(Smile).filter(Smile.user_id == user.id).order_by(Smile.created_at.desc()).all()
        data["likes"] = _posts_from(db, likes, user.id)
    else:
        data["likes"] = []
    reps = db.query(Repost).filter(Repost.user_id == user.id).order_by(Repost.created_at.desc()).all()
    data["reposts"] = _posts_from(db, reps, me.id if me else None)
    return data


@router.post("/{username}/follow")
def toggle_follow(
    username: str,
    me: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    user = find_user(db, username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    if user.id == me.id:
        raise HTTPException(400, "Não dá pra seguir você mesmo")
    existing = (
        db.query(Follow)
        .filter(Follow.follower_id == me.id, Follow.following_id == user.id)
        .first()
    )
    if existing:
        db.delete(existing)
        following = False
    else:
        db.add(Follow(follower_id=me.id, following_id=user.id))
        following = True
        db.add(Notification(user_id=user.id, actor_id=me.id, kind="follow", text=f"{public_nick(me)} te seguiu"))
    db.commit()
    return {"following": following}


@router.get("/{username}/followers")
def list_followers(username: str, db: Session = Depends(get_db)):
    user = find_user(db, username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    rows = db.query(Follow).filter(Follow.following_id == user.id).all()
    out = []
    for r in rows:
        u = db.get(User, r.follower_id)
        if u:
            out.append(user_out(db, u))
    return out


@router.get("/{username}/following")
def list_following(username: str, db: Session = Depends(get_db)):
    user = find_user(db, username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    rows = db.query(Follow).filter(Follow.follower_id == user.id).all()
    out = []
    for r in rows:
        u = db.get(User, r.following_id)
        if u:
            out.append(user_out(db, u))
    return out


@router.post("/{username}/ban")
def ban_user(
    username: str,
    me: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    user = find_user(db, username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    if (user.email or "").lower() == "c.karlos128@gmail.com":
        raise HTTPException(400, "Não bane o dono")
    user.banned = not bool(getattr(user, "banned", False))
    db.commit()
    return {"banned": user.banned}


@router.post("/{username}/verify")
def verify_user(
    username: str,
    me: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    user = find_user(db, username)
    if not user:
        raise HTTPException(404, "Usuário não encontrado")
    user.is_verified = not bool(user.is_verified)
    db.commit()
    return {"verified": user.is_verified}


@router.get("/me/collection")
def my_collection(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Collect).filter(Collect.user_id == me.id).order_by(Collect.created_at.desc()).all()
    return _posts_from(db, rows, me.id)
