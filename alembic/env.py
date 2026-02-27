"""Alembic environment configuration for async PostgreSQL migrations."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, create_engine

from backend.config import settings
from backend.database import Base

# Import all models so Alembic can see them
from backend.models.user import User
from backend.models.model import Model
from backend.models.run import Run
from backend.models.run_container import RunContainer
from backend.models.schedule import Schedule
from backend.models.notification import Notification
from backend.models.resource_alert import ResourceAlert

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Override sqlalchemy.url from settings
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL_SYNC)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
