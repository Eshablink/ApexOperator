from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from apexoperator.persistence.models import Base


def make_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def _add_column_if_missing(connection, table: str, column: str) -> None:
    columns = {item["name"] for item in inspect(connection).get_columns(table)}
    if column not in columns:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} VARCHAR(128) NOT NULL DEFAULT 'default'"))


def init_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        _add_column_if_missing(connection, "tasks", "organization_id")
        _add_column_if_missing(connection, "users", "organization_id")
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_organization_id ON tasks (organization_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_users_organization_id ON users (organization_id)"))
        connection.execute(text("DROP INDEX IF EXISTS uq_tasks_invoice_id"))
        connection.execute(text("""
            DELETE FROM tasks
            WHERE task_id IN (
                SELECT task_id FROM (
                    SELECT task_id,
                           ROW_NUMBER() OVER (
                               PARTITION BY organization_id, invoice_id
                               ORDER BY created_at DESC, task_id DESC
                           ) AS row_number
                    FROM tasks
                ) ranked
                WHERE ranked.row_number > 1
            )
        """))
        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_tasks_org_invoice ON tasks (organization_id, invoice_id)"))


def make_session_factory(engine: Engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
