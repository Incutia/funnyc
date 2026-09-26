from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_member
from app.database import get_db
from app.models import Message, Notification, User
from app.routers.users import find_user
from app.storage import save_into
from app.utils import abs_url, public_nick
from pathlib import Path
import uuid

router = APIRouter()


class ChatIn(BaseModel):
    text: str = Field(default="", max_length=500)


def _out(db, m: Message, me_id: int):
    s = db.get(User, m.sender_id)
    r = db.get(User, m.receiver_id)
    return {
        "id": m.id,
        "text": m.text or "",
        "media_url": abs_url(m.media_url or ""),
        "mine": m.sender_id == me_id,
        "from": public_nick(s) if s else "",
        "to": public_nick(r) if r else "",
        "created_at": m.created_at.isoformat() if m.created_at else "",
    }


@router.get("/inbox")
def inbox(me: User = Depends(require_member), db: Session = Depends(get_db)):
    rows = (
        db.query(Message)
        .filter((Message.sender_id == me.id) | (Message.receiver_id == me.id))
        .order_by(Message.created_at.desc())
        .limit(200)
        .all()
    )
    seen = set()
    out = []
    for m in rows:
        other = m.receiver_id if m.sender_id == me.id else m.sender_id
        if other in seen:
            continue
        seen.add(other)
        u = db.get(User, other)
        out.append(
            {
                "username": public_nick(u) if u else "?",
                "avatar_url": (u.avatar_url if u else "") or "",
                "last": m.text,
            }
        )
    return out


@router.get("/{username}")
def thread(username: str, me: User = Depends(require_member), db: Session = Depends(get_db)):
    other = find_user(db, username)
    if not other:
        raise HTTPException(404, "Usuário não encontrado")
    rows = (
        db.query(Message)
        .filter(
            ((Message.sender_id == me.id) & (Message.receiver_id == other.id))
            | ((Message.sender_id == other.id) & (Message.receiver_id == me.id))
        )
        .order_by(Message.created_at.asc())
        .limit(200)
        .all()
    )
    return [_out(db, m, me.id) for m in rows]


@router.post("/{username}")
def send(username: str, body: ChatIn, me: User = Depends(require_member), db: Session = Depends(get_db)):
    other = find_user(db, username)
    if not other:
        raise HTTPException(404, "Usuário não encontrado")
    if other.id == me.id:
        raise HTTPException(400, "Não manda mensagem pra você")
    if not body.text.strip():
        raise HTTPException(400, "Escreve algo")
    m = Message(sender_id=me.id, receiver_id=other.id, text=body.text.strip())
    db.add(m)
    db.add(Notification(user_id=other.id, actor_id=me.id, kind="chat", text=f"{public_nick(me)} mandou mensagem"))
    db.commit()
    db.refresh(m)
    return _out(db, m, me.id)


@router.post("/{username}/foto")
def send_photo(
    username: str,
    file: UploadFile = File(...),
    me: User = Depends(require_member),
    db: Session = Depends(get_db),
):
    other = find_user(db, username)
    if not other:
        raise HTTPException(404, "Usuário não encontrado")
    suffix = Path(file.filename or "chat.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        raise HTTPException(400, "Só foto")
    data = file.file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "Foto máx 15MB")
    name = f"{uuid.uuid4().hex}{suffix}"
    url = save_into(me, "memes", name, data)
    m = Message(sender_id=me.id, receiver_id=other.id, text="", media_url=url)
    db.add(m)
    db.add(Notification(user_id=other.id, actor_id=me.id, kind="chat", text=f"{public_nick(me)} mandou foto"))
    db.commit()
    db.refresh(m)
    return _out(db, m, me.id)
