from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "mude-isso-no-servidor-funnyc-super-secreto"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 30
    DATABASE_URL: str = "sqlite:///./data/funnyc.db"
    UPLOAD_DIR: str = "./data/uploads"
    PUBLIC_BASE_URL: str = "http://127.0.0.1:8000"
    FEATURED_SMILE_THRESHOLD: int = 5
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "Funnyc <noreply@funnyc.com.br>"

    class Config:
        env_file = ".env"


settings = Settings()
