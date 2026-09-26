"""Funnyc API — meme app like iFunny."""
from pathlib import Path
from time import time

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import require_owner
from app.config import settings
from app.database import Base, engine, migrate
from app.models import User
from app.routers import auth, comments, feed, posts, profile, users

Base.metadata.create_all(bind=engine)
migrate()
try:
    from seed import run as seed_run
    seed_run()
except Exception:
    pass

WEB = Path(__file__).resolve().parent.parent / "web"
STARTED = int(time())

app = FastAPI(title="Funnyc", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

uploads = Path(settings.UPLOAD_DIR)
uploads.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(uploads)), name="media")
if WEB.exists():
    app.mount("/web", StaticFiles(directory=str(WEB)), name="web")

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(feed.router, prefix="/api/feed", tags=["feed"])
app.include_router(posts.router, prefix="/api/posts", tags=["posts"])
app.include_router(comments.router, prefix="/api/comments", tags=["comments"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])


@app.get("/api/health")
def health():
    return {"ok": True, "app": "funnyc", "v": "juice-4"}


@app.get("/api/admin/pastas")
def list_user_folders(me: User = Depends(require_owner)):
    root = Path(settings.UPLOAD_DIR) / "usuarios"
    if not root.exists():
        return {"pastas": []}
    out = []
    for p in sorted(root.iterdir()):
        if p.is_dir():
            out.append(
                {
                    "nick": p.name,
                    "perfil": [x.name for x in (p / "perfil").glob("*")],
                    "memes": [x.name for x in (p / "memes").glob("*")],
                    "videos": [x.name for x in (p / "videos").glob("*")],
                    "escreveu": [x.name for x in (p / "escreveu").glob("*")],
                }
            )
    return {"pasta": str(root), "usuarios": out}


@app.get("/api/version")
def version():
    stamp = STARTED
    if WEB.exists():
        for p in WEB.glob("*"):
            stamp = max(stamp, int(p.stat().st_mtime))
    return {"v": stamp}


@app.get("/")
def home():
    index = WEB / "index.html"
    if index.exists():
        return FileResponse(
            index,
            headers={"Cache-Control": "no-store, max-age=0"},
        )
    return {"ok": True, "app": "Funnyc"}
