from datetime import datetime
from pathlib import Path
import re

from app.config import settings

SAFE = re.compile(r"[^a-z0-9_]+")


def slug(name: str) -> str:
    s = SAFE.sub("_", (name or "user").lower()).strip("_")
    return (s[:32] or "user")


def user_dir(username: str) -> Path:
    root = Path(settings.UPLOAD_DIR) / "usuarios" / slug(username)
    for part in ("perfil", "memes", "videos", "escreveu"):
        (root / part).mkdir(parents=True, exist_ok=True)
    return root


def write_conta(user) -> None:
    folder = user_dir(user.username)
    path = folder / "conta.txt"
    lines = [
        f"nick: {getattr(user, 'display_name', '') or user.username}",
        f"usuario: {user.username}",
        f"email: {user.email}",
        f"senha: [hash] {user.password_hash[:24]}..." if user.password_hash else "senha: (sem senha / anon)",
        "obs: a senha real nao e gravada em texto. so o hash.",
        f"atualizado: {datetime.utcnow().isoformat()}Z",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def save_into(user, kind: str, filename: str, data: bytes) -> str:
    folder = user_dir(user.username)
    write_conta(user)
    dest = folder / kind / filename
    dest.write_bytes(data)
    rel = dest.relative_to(Path(settings.UPLOAD_DIR)).as_posix()
    return f"/media/{rel}"


def log_texto(user, texto: str) -> None:
    folder = user_dir(user.username)
    write_conta(user)
    path = folder / "escreveu" / "historico.txt"
    stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{stamp}] {texto}\n")
