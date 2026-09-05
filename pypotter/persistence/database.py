from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)


def make_session_factory(database_url: str):
    return sessionmaker(bind=make_engine(database_url), autoflush=False, expire_on_commit=False)


def session_dependency(factory) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
    finally:
        session.close()
