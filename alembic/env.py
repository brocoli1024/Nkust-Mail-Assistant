"""Migration entry point for the new database only."""
from alembic import context

from app.config import Settings
from app.database.multi_user import create_multi_user_engine, reject_legacy_schema, validate_database_url
from app.models.multi_user import MultiUserBase

config = context.config
target_metadata = MultiUserBase.metadata


def run():
    settings = Settings.load()
    # attributes are used by tests/tools; secrets need not pass through ConfigParser.
    url = validate_database_url(config.attributes.get('database_url') or settings.database_url,
                                legacy_path=settings.database_path)
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=target_metadata, literal_binds=True,
                          dialect_opts={'paramstyle': 'named'}, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_multi_user_engine(url, legacy_path=settings.database_path)
    try:
        with engine.connect() as connection:
            reject_legacy_schema(connection)
            connection.rollback()  # inspection starts an implicit transaction
            context.configure(connection=connection, target_metadata=target_metadata,
                              compare_type=True, render_as_batch=connection.dialect.name == 'sqlite')
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


run()
