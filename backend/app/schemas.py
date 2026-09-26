from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    username: str = Field(default="", max_length=32)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: str
    password: str


class ForgotPassword(BaseModel):
    email: str


class ResetPassword(BaseModel):
    email: str
    code: str
    new_password: str = Field(min_length=6, max_length=128)


class GoogleStart(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    bio: str = Field(default="", max_length=200)
    id_token: str = ""


class UserOut(BaseModel):
    id: int
    username: str
    bio: str = ""
    avatar_url: str = ""
    banner_url: str = ""
    created_at: datetime
    followers: int = 0
    following: int = 0
    posts_count: int = 0
    is_anonymous: bool = False
    is_admin: bool = False
    is_verified: bool = False

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class PostOut(BaseModel):
    id: int
    user_id: int
    username: str
    avatar_url: str = ""
    kind: str
    media_url: str
    caption: str
    tags: list[str] = []
    smiles_count: int
    comments_count: int
    reposts_count: int = 0
    featured: bool
    smiled: bool = False
    collected: bool = False
    reposted: bool = False
    author_verified: bool = False
    created_at: datetime


class CommentCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    parent_id: Optional[int] = None


class CommentOut(BaseModel):
    id: int
    user_id: int
    username: str
    avatar_url: str = ""
    text: str
    parent_id: Optional[int] = None
    likes_count: int = 0
    liked: bool = False
    featured: bool = False
    verified: bool = False
    created_at: datetime


class ProfileUpdate(BaseModel):
    username: Optional[str] = Field(default=None, min_length=3, max_length=32)
    bio: Optional[str] = Field(default=None, max_length=200)
    avatar_url: Optional[str] = None
    banner_url: Optional[str] = None
