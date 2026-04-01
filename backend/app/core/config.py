"""
Petal Backend — Application Configuration
"""
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # === Application ===
    PROJECT_NAME: str = "Petal"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # === CORS ===
    CORS_ORIGINS: List[str] = ["https://servicewechat.com"]

    # === Database ===
    DATABASE_URL: str = "postgresql+asyncpg://petal:petal@localhost:5432/petal"

    # === Redis ===
    REDIS_URL: str = "redis://localhost:6379/0"

    # === JWT ===
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # === WeChat ===
    WECHAT_APP_ID: str = ""
    WECHAT_APP_SECRET: str = ""

    # === AI ===
    AI_PROVIDER: str = "openai"  # openai | baidu | local
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    BAIDU_API_KEY: str = ""
    BAIDU_SECRET_KEY: str = ""

    # === Object Storage (MinIO / S3) ===
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_SKIN: str = "petal-skin-images"
    S3_BUCKET_PRODUCTS: str = "petal-products"

    # === Celery ===
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # === Rate Limiting ===
    ANTI_FAKE_RATE_LIMIT_USER: int = 10      # per minute
    ANTI_FAKE_RATE_LIMIT_IP: int = 30        # per minute
    SKIN_ANALYSIS_DAILY_LIMIT: int = 20      # per day per user

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
