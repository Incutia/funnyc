from app.models import Collect, Follow, Post, Repost, Smile, User
from app.schemas import PostOut, UserOut
from app.config import settings

OWNER_EMAIL = "c.karlos128@gmail.com"


def is_owner(user: User | None) -> bool:
    return bool(user and (user.email or "").lower() == OWNER_EMAIL)


def is_staff(user: User | None) -> bool:
    return bool(user and (is_owner(user) or getattr(user, "is_admin", False) or getattr(user, "is_moderator", False)))


def mark_owner(user: User) -> User:
    if is_owner(user):
        user.is_admin = True
        user.is_verified = True
        user.is_moderator = True
    return user


def public_nick(user: User) -> str:
    name = (getattr(user, "display_name", "") or "").strip()
    return name or user.username


def abs_url(path: str) -> str:
    if not path:
        return ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def parse_tags(raw: str) -> list[str]:
    if not raw:
        return []
    parts = [t.strip().lstrip("#").lower() for t in raw.replace(",", " ").split()]
    return [t for t in parts if t][:8]


def user_out(db, user: User) -> UserOut:
    followers = db.query(Follow).filter(Follow.following_id == user.id).count()
    following = db.query(Follow).filter(Follow.follower_id == user.id).count()
    posts_count = db.query(Post).filter(Post.user_id == user.id).count()
    return UserOut(
        id=user.id,
        username=public_nick(user),
        bio=user.bio or "",
        avatar_url=abs_url(user.avatar_url or ""),
        banner_url=abs_url(getattr(user, "banner_url", "") or ""),
        created_at=user.created_at,
        followers=followers,
        following=following,
        posts_count=posts_count,
        is_anonymous=bool(getattr(user, "is_anonymous", False)),
        is_admin=bool(getattr(user, "is_admin", False) or is_owner(user)),
        is_verified=bool(getattr(user, "is_verified", False) or is_owner(user)),
        is_moderator=bool(getattr(user, "is_moderator", False) or is_owner(user)),
    )


def post_out(db, post: Post, me_id: int | None = None) -> PostOut:
    author = db.get(User, post.user_id)
    smiled = False
    collected = False
    reposted = False
    if me_id:
        smiled = (
            db.query(Smile).filter(Smile.user_id == me_id, Smile.post_id == post.id).first()
            is not None
        )
        collected = (
            db.query(Collect).filter(Collect.user_id == me_id, Collect.post_id == post.id).first()
            is not None
        )
        reposted = (
            db.query(Repost).filter(Repost.user_id == me_id, Repost.post_id == post.id).first()
            is not None
        )
    return PostOut(
        id=post.id,
        user_id=post.user_id,
        username=public_nick(author) if author else "deleted",
        avatar_url=abs_url(author.avatar_url or "") if author else "",
        kind=post.kind,
        media_url=abs_url(post.media_url),
        caption=post.caption or "",
        tags=parse_tags(post.tags or ""),
        smiles_count=post.smiles_count,
        comments_count=post.comments_count,
        reposts_count=getattr(post, "reposts_count", 0) or 0,
        featured=post.featured,
        smiled=smiled,
        collected=collected,
        reposted=reposted,
        author_verified=bool(author and (getattr(author, "is_verified", False) or is_owner(author))),
        author_moderator=bool(author and getattr(author, "is_moderator", False) and not is_owner(author)),
        views_count=getattr(post, "views_count", 0) or 0,
        created_at=post.created_at,
    )
