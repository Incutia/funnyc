from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_member, require_owner
from app.database import get_db
from app.models import Message, Notification, User
from app.routers.users import find_user
from app.utils import public_nick

router = APIRouter()


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class BlastIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    username: str = ""


def _out(db, m: Message, me_id: int):
    s = db.get(User, m.sender_id)
    r = db.get(User, m.receiver_id)
    return {
        "id": m.id,
        "text": m.text,
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
    m = Message(sender_id=me.id, receiver_id=other.id, text=body.text.strip())
    db.add(m)
    db.add(Notification(user_id=other.id, actor_id=me.id, kind="chat", text=f"{public_nick(me)} mandou mensagem"))
    db.commit()
    db.refresh(m)
    return _out(db, m, me.id)
