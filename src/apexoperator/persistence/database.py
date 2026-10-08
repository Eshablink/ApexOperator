from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from apexoperator.persistence.models import Base


def make_engine(database_url: str) -> Engine:
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


def init_database(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    # create_all() does not add constraints to an already-existing table.\n    # Keep deployed databases aligned with the model-level uniqueness guarantee.\n    with engine.begin() as connection:\n        connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_tasks_invoice_id ON tasks (invoice_id)"))


def make_session_factory(engine: Engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
