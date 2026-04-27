"""Application configuration via Pydantic Settings, loaded from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Central configuration for the Financial Model Execution Platform."""

    # Application mode: "develop" or "production"
    APP_MODE: str = Field(default="develop", description="Application mode: develop or production")

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://almplatform:almplatform@localhost:5432/almplatform",
        description="Async PostgreSQL connection string",
    )
    DATABASE_URL_SYNC: str = Field(
        default="postgresql+psycopg2://almplatform:almplatform@localhost:5432/almplatform",
        description="Sync PostgreSQL connection string for Alembic/Celery",
    )

    # Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")

    # LDAP
    LDAP_URL: str = Field(default="ldap://localhost:389", description="LDAP server URL")
    LDAP_BASE_DN: str = Field(default="dc=example,dc=com", description="LDAP base DN for searches")

    # JWT
    JWT_SECRET: str = Field(default="change-me-in-production", description="JWT signing secret")
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=480, description="Access token TTL in minutes")
    REFRESH_TOKEN_EXPIRE_MINUTES: int = Field(default=10080, description="Refresh token TTL in minutes (7 days)")

    # SMTP
    SMTP_HOST: str = Field(default="localhost", description="SMTP server host")
    SMTP_PORT: int = Field(default=587, description="SMTP server port")
    SMTP_FROM: str = Field(default="almplatform@example.com", description="From address for emails")

    # Paths
    SHARED_NAS_PATH: str = Field(default="/mnt/nas/shared", description="NAS mount point for shared data")
    RUNS_BASE_PATH: str = Field(default="/data/runs", description="Base path for run output directories")
    ARCHIVE_BASE_PATH: str = Field(default="/data/archive", description="Base path for archived runs")
    MARIMO_BASE_PATH: str = Field(default="/data/marimo", description="Base path for Marimo notebooks")

    # Resource thresholds
    MEMORY_THRESHOLD: float = Field(default=0.80, description="Memory usage threshold (0.0–1.0)")
    CPU_ALERT_THRESHOLD: float = Field(default=0.90, description="CPU usage alert threshold (0.0–1.0)")
    ALERT_COOLDOWN_MINUTES: int = Field(default=30, description="Minutes between resource alert emails")

    # Smart concurrency — total resource budgets for all concurrent containers
    MAX_TOTAL_MEMORY_PCT: float = Field(default=0.80, description="Max fraction of total server memory for concurrent containers (0.0–1.0)")
    MAX_TOTAL_CPU_PERCENT: float = Field(default=400.0, description="Max total CPU% for concurrent containers (100 = 1 core)")

    # App URL for email links
    APP_BASE_URL: str = Field(default="http://localhost", description="Base URL for generating links in emails")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

    @property
    def is_develop(self) -> bool:
        """Check if running in develop mode."""
        return self.APP_MODE == "develop"


settings = Settings()

# ──────────────────────────────────────────────
# Dev-mode bypass users (no LDAP/DB required)
# ──────────────────────────────────────────────
DEV_USERS = {
    "admin": {
        "id": "00000000-0000-0000-0000-000000000001",
        "password": "admin123",
        "email": "admin@dev.local",
        "role": "admin",
    },
    "developer": {
        "id": "00000000-0000-0000-0000-000000000002",
        "password": "dev123",
        "email": "developer@dev.local",
        "role": "developer",
    },
    "runner": {
        "id": "00000000-0000-0000-0000-000000000003",
        "password": "runner123",
        "email": "runner@dev.local",
        "role": "runner",
    },
}
