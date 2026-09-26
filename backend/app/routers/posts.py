from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session
from pathlib import Path
import uuid

from app.auth import get_current_user, get_optional_user, require_member
from app.config import settings
from app.database import get_db
from app.models import Collect, Post, Report, Repost, Smile, User
from app.utils import parse_tags, post_out
from app.storage import log_texto, save_into

router = APIRouter()

ALLOWED_IMG = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_VID = {".mp4", ".webm"}
ALLOWED = ALLOWED_IMG | ALLOWED_VID
IMG_MAX = 15 * 1024 * 1024
VID_MAX = 200 * 1024 * 1024


def _save_upload(file: UploadFile, user: User | None = None) -> tuple[str, str]:
    suffix = Path(file.filename or "meme.jpg").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(400, "Use jpg, png, gif, webp, mp4 ou webm")
    data = file.file.read()
    limit = VID_MAX if suffix in ALLOWED_VID else IMG_MAX
    if len(data) > limit:
        raise HTTPException(400, "Vídeo máx 200MB. Foto/GIF máx 15MB")
    name = f"{uuid.uuid4().hex}{suffix}"
    kind = "video" if suffix in ALLOWED_VID else "image"
    if user is not None:
        folder = "videos" if kind == "video" else "memes"
        url = save_into(user, folder, name, data)
        return url, kind
    dest_dir = Path(settings.UPLOAD_DIR)
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / name).write_bytes(data)
    return f"/media/{name}", kind


@router.post("")
def create_post(
    caption: str = Form(""),
    tags: str = Form(""),
    kind: str = Form("image"),
    media_url: str = Form(""),
    file: UploadFile | None = File(None),
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    if file is not None and file.filename:
        url, kind = _save_upload(file, user)
        log_texto(user, f"postou {kind} {url} caption={caption.strip()[:80]}")
    elif media_url.strip():
        url = media_url.strip()
        kind = kind if kind in ("image", "video") else "image"
    else:
        raise HTTPException(400, "Envie um arquivo")
    tag_str = ",".join(parse_tags(tags))
    post = Post(
        user_id=user.id,
        kind=kind if kind in ("image", "video") else "image",
        media_url=url,
        caption=caption.strip()[:300],
        tags=tag_str,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post_out(db, post, user.id)


@router.get("/{post_id}")
def get_post(
    post_id: int,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Meme não encontrado")
    return post_out(db, post, me.id if me else None)


@router.post("/{post_id}/view")
def add_view(post_id: int, db: Session = Depends(get_db)):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Meme não encontrado")
    post.views_count = (getattr(post, "views_count", 0) or 0) + 1
    db.commit()
    return {"ok": True, "views": post.views_count}


@router.post("/{post_id}/smile")
def toggle_smile(
    post_id: int,
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Meme não encontrado")
    existing = db.query(Smile).filter(Smile.user_id == user.id, Smile.post_id == post.id).first()
    if existing:
        db.delete(existing)
        post.smiles_count = max(0, post.smiles_count - 1)
        smiled = False
    else:
        db.add(Smile(user_id=user.id, post_id=post.id))
        post.smiles_count += 1
        smiled = True
        if post.smiles_count >= settings.FEATURED_SMILE_THRESHOLD:
            post.featured = True
    db.commit()
    db.refresh(post)
    out = post_out(db, post, user.id)
    out.smiled = smiled
    return out


@router.post("/{post_id}/collect")
def toggle_collect(
    post_id: int,
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Meme não encontrado")
    existing = db.query(Collect).filter(Collect.user_id == user.id, Collect.post_id == post.id).first()
    if existing:
        db.delete(existing)
        collected = False
    else:
        db.add(Collect(user_id=user.id, post_id=post.id))
        collected = True
    db.commit()
    db.refresh(post)
    out = post_out(db, post, user.id)
    out.collected = collected
    return out


@router.post("/{post_id}/repost")
def toggle_repost(
    post_id: int,
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Meme não encontrado")
    existing = db.query(Repost).filter(Repost.user_id == user.id, Repost.post_id == post.id).first()
    if existing:
        db.delete(existing)
        post.reposts_count = max(0, (post.reposts_count or 0) - 1)
        flag = False
    else:
        db.add(Repost(user_id=user.id, post_id=post.id))
        post.reposts_count = (post.reposts_count or 0) + 1
        flag = True
    db.commit()
    db.refresh(post)
    out = post_out(db, post, user.id)
    out.reposted = flag
    return out


@router.get("")
def list_by_tag(
    tag: str = Query(""),
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    me: User | None = Depends(get_optional_user),
):
    q = db.query(Post)
    if tag:
        q = q.filter(Post.tags.ilike(f"%{tag.strip().lstrip('#').lower()}%"))
    posts = q.order_by(Post.created_at.desc()).offset(skip).limit(min(limit, 50)).all()
    return [post_out(db, p, me.id if me else None) for p in posts]


@router.delete("/{post_id}")
def delete_post(
    post_id: int,
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Meme não encontrado")
    if post.user_id != user.id and not (getattr(user, "is_admin", False) or (user.email or "").lower() == "c.karlos128@gmail.com"):
        raise HTTPException(403, "Só o autor ou o dono pode apagar")
    db.query(Smile).filter(Smile.post_id == post.id).delete()
    db.query(Collect).filter(Collect.post_id == post.id).delete()
    db.query(Repost).filter(Repost.post_id == post.id).delete()
    db.delete(post)
    db.commit()
    return {"ok": True}


@router.post("/{post_id}/feature")
def toggle_feature(
    post_id: int,
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    if not (getattr(user, "is_admin", False) or (user.email or "").lower() == "c.karlos128@gmail.com"):
        raise HTTPException(403, "Só o dono destaca")
    post = db.get(Post, post_id)
    if not post:
        raise HTTPException(404, "Meme não encontrado")
    post.featured = not post.featured
    db.commit()
    db.refresh(post)
    return post_out(db, post, user.id)


@router.post("/{post_id}/report")
def report_post(
    post_id: int,
    reason: str = Form("denuncia"),
    user: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    if not db.get(Post, post_id):
        raise HTTPException(404, "Meme não encontrado")
    db.add(Report(user_id=user.id, post_id=post_id, reason=reason[:200]))
    db.commit()
    return {"ok": True}
