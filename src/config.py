from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):

    # App
    APP_NAME: str = "ArxivAI v2.0"
    APP_VERSION: str = "2.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # FastAPI
    FASTAPI_HOST: str = "0.0.0.0"
    FASTAPI_PORT: int = 8000
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    ALLOW_CREDENTIALS: bool = True
    ALLOW_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
    ALLOW_HEADERS: List[str] = ["*"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/arxivai"
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 5

    # JWT
    JWT_SECRET: str = "change-this-secret"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # Chroma
    CHROMA_PATH: str = "./data/chroma_db"

    # Embeddings
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"
    EMBEDDING_DEVICE: str = "cpu"

    # LLM API Keys — at least ONE required
    GROQ_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    AZURE_OPENAI_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_DEPLOYMENT_NAME: str = "text-embedding-3-small"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_DEFAULT_REGION: str = "us-east-1"
    AWS_API_KEY: str = ""

    # LLM defaults
    DEFAULT_LLM_MODE: str = "balanced"

    # S3 / MinIO
    S3_ENDPOINT: str = "http://localhost:9000"
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET: str = "arxivai-papers"
    S3_REGION: str = "us-east-1"
    S3_USE_SSL: bool = False

    # Monitoring
    PROMETHEUS_PORT: int = 9090
    LOG_LEVEL: str = "INFO"

    # Quality thresholds
    RAGAS_THRESHOLD: float = 0.7
    REFINEMENT_MAX_LOOPS: int = 3
    MIN_RETRIEVAL_SCORE: float = 0.6

    # Limits
    MAX_QUERIES_PER_MINUTE: int = 30
    MAX_UPLOADS_PER_DAY: int = 10
    PDF_MAX_SIZE_MB: int = 50

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


settings = get_settings()