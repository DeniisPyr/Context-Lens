from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from context_lens.db.models import Base
from context_lens.settings import DatabaseSettings

config = context.config
target_metadata = Base.metadata

if config.config_file_name is not None:
    # The default disables every logger that already exists in this process.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Used directly, not through config.set_main_option: Alembic's config reads % as
# interpolation, and URL-encoded passwords contain it.
url = DatabaseSettings().database_url.get_secret_value()


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(url, poolclass=NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
