import json
from urllib.request import Request, urlopen
from urllib.error import URLError

from app.config import settings


def send_mail(to: str, subject: str, text: str) -> bool:
    key = (settings.RESEND_API_KEY or "").strip()
    if not key:
        return False
    payload = json.dumps(
        {
            "from": settings.EMAIL_FROM,
            "to": [to],
            "subject": subject,
            "text": text,
        }
    ).encode()
    req = Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as r:
            r.read()
        return True
    except URLError:
        return False


def send_code(to: str, code: str, kind: str) -> bool:
    if kind == "confirm":
        subject = "Confirma sua conta Funnyc"
        body = f"Seu código de confirmação é {code}. Vale 20 minutos."
    else:
        subject = "Reset de senha Funnyc"
        body = f"Seu código para nova senha é {code}. Vale 20 minutos."
    return send_mail(to, subject, body)
