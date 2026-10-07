from pathlib import Path

from sqlalchemy import create_engine, inspect, text
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
    inspector = inspect(engine)
    existing = {column["name"] for column in inspector.get_columns("tasks")}
    missing = {
        "planner_mode": "VARCHAR(32)",
        "planner_model": "VARCHAR(128)",
    }
    with engine.begin() as connection:
        for name, sql_type in missing.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE tasks ADD COLUMN {name} {sql_type}"))


def make_session_factory(engine: Engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
