from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.auth import require_member
from app.database import get_db
from app.models import User
from app.routers.users import _save_pic
from app.utils import user_out

router = APIRouter()


@router.post("/avatar")
def avatar(file: UploadFile = File(...), me: User = Depends(require_member), db: Session = Depends(get_db)):
    me.avatar_url = _save_pic(file, "av", me)
    db.commit()
    db.refresh(me)
    return user_out(db, me)


@router.post("/banner")
def banner(file: UploadFile = File(...), me: User = Depends(require_member), db: Session = Depends(get_db)):
    me.banner_url = _save_pic(file, "bn", me)
    db.commit()
    db.refresh(me)
    return user_out(db, me)
