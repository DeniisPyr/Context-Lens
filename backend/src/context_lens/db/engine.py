from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from context_lens.settings import DatabaseSettings


def create_database_engine(settings: DatabaseSettings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url.get_secret_value(),
        # Tests each connection before use and replaces a dead one, so the app recovers
        # by itself after the database restarts.
        pool_pre_ping=True,
        # SQLAlchemy puts a statement's parameters into its error messages, and here
        # those would be the document's text.
        hide_parameters=True,
    )
