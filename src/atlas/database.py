import os
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://atlas:atlas@127.0.0.1:5432/atlas"
    )


def get_session(request: Request) -> Iterator[Session]:
    with Session(request.app.state.engine) as session:
        yield session
