import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import create_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.models import PasswordReset, User
from app.schemas import ForgotPassword, ResetPassword, TokenOut, UserCreate, UserLogin
from app.utils import mark_owner, user_out
from app.storage import user_dir, write_conta

router = APIRouter()


def _token(db, user: User) -> TokenOut:
    return TokenOut(access_token=create_token(user.id, user.username), user=user_out(db, user))


def _nick_from_email(email: str) -> str:
    base = "".join(ch for ch in email.split("@")[0].lower() if ch.isalnum() or ch == "_")[:24]
    return base or "user"


@router.post("/register", response_model=TokenOut)
def register(body: UserCreate, db: Session = Depends(get_db)):
    email = body.email.lower()
    username = body.username.strip().lower() if body.username else _nick_from_email(email)
    if not username.replace("_", "").isalnum():
        raise HTTPException(400, "Username só pode ter letras, números e _")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email já cadastrado")
    if db.query(User).filter(User.username == username).first():
        username = f"{username}{secrets.token_hex(2)}"
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(body.password),
        is_anonymous=False,
    )
    mark_owner(user)
    db.add(user)
    db.commit()
    db.refresh(user)
    user_dir(user.username)
    write_conta(user)
    return _token(db, user)


@router.post("/login", response_model=TokenOut)
def login(body: UserLogin, db: Session = Depends(get_db)):
    key = body.email.strip().lower()
    user = db.query(User).filter(User.email == key).first()
    if not user:
        user = db.query(User).filter(User.username == key).first()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email ou senha errados")
    if user.is_anonymous:
        raise HTTPException(401, "Conta anônima")
    mark_owner(user)
    db.commit()
    user_dir(user.username)
    write_conta(user)
    return _token(db, user)


@router.post("/anonymous", response_model=TokenOut)
def anonymous(db: Session = Depends(get_db)):
    suffix = secrets.token_hex(3)
    username = f"anon_{suffix}"
    user = User(
        username=username,
        email=f"{username}@anon.funnyc",
        password_hash="",
        bio="",
        is_anonymous=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token(db, user)


@router.post("/forgot")
def forgot(body: ForgotPassword, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or user.is_anonymous:
        return {"ok": True, "message": "Se o email existir, o código foi gerado."}
    code = f"{secrets.randbelow(1000000):06d}"
    db.query(PasswordReset).filter(PasswordReset.email == email, PasswordReset.used.is_(False)).delete()
    db.add(
        PasswordReset(
            email=email,
            code_hash=hash_password(code),
            expires_at=datetime.utcnow() + timedelta(minutes=20),
        )
    )
    db.commit()
    return {
        "ok": True,
        "message": "Código gerado. Sem SMTP no Railway o código vem aqui pra testar.",
        "code": code,
    }


@router.post("/reset")
def reset(body: ResetPassword, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    row = (
        db.query(PasswordReset)
        .filter(PasswordReset.email == email, PasswordReset.used.is_(False))
        .order_by(PasswordReset.id.desc())
        .first()
    )
    if not row or row.expires_at < datetime.utcnow():
        raise HTTPException(400, "Código expirado. Pede outro.")
    if not verify_password(body.code.strip(), row.code_hash):
        raise HTTPException(400, "Código inválido")
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(404, "Conta não encontrada")
    user.password_hash = hash_password(body.new_password)
    row.used = True
    db.commit()
    return _token(db, user)


@router.get("/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_out(db, user)
