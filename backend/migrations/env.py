"""Alembic environment: the app's settings and models are the single source of truth."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app.core.config import get_settings
from app.infrastructure.database import get_engine
from app.infrastructure.models import Base

config = context.config
# Tests pass their own connection to the disposable test database (see tests/integration/test_migrations.py).
test_connection: Connection | None = config.attributes.get("connection")

if config.config_file_name is not None and test_connection is None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url,  # only picks the SQL dialect; nothing connects
        target_metadata=Base.metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
elif test_connection is not None:
    run_migrations(test_connection)
else:
    with get_engine().connect() as connection:
        run_migrations(connection)
