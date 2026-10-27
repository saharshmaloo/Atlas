import os
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from atlas.main import create_app
from atlas.workspaces import Workspace

pytestmark = pytest.mark.database


@pytest.fixture
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")
    # Never migrate or clear the supplied database: create and drop our own.
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    name = f"atlas_test_{uuid4().hex}"
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    test_url = make_url(url).set(database=name)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = test_url
    try:
        command.upgrade(config, "head")
        yield test_url, config
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture
def client(database):
    with TestClient(create_app(database[0])) as client:
        yield client


def test_workspace_survives_app_restart(database):
    url, _ = database
    with TestClient(create_app(url)) as client:
        response = client.post("/workspaces", json={"name": "  Distributed Databases  "})
        assert response.status_code == 201
        workspace = response.json()
        assert UUID(workspace["id"]).version == 4
        assert workspace["name"] == "Distributed Databases"
        assert datetime.fromisoformat(workspace["created_at"]).tzinfo is not None
    # A separate engine and application must find the committed row.
    with TestClient(create_app(url)) as client:
        response = client.get(f'/workspaces/{workspace["id"]}')
        assert response.status_code == 200
        assert response.json() == workspace


@pytest.mark.parametrize("body", [{}, {"name": ""}, {"name": " \t\n"}, {"name": "a" * 201}, {"name": None}, {"name": 123}])
def test_invalid_workspace_is_not_saved(client, body):
    assert client.post("/workspaces", json=body).status_code == 422
    with Session(client.app.state.engine) as session:
        assert session.scalar(select(Workspace)) is None


def test_workspace_name_boundary_and_distinct_ids(client):
    first = client.post("/workspaces", json={"name": "a" * 200})
    second = client.post("/workspaces", json={"name": "a" * 200})
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_missing_workspace(client):
    response = client.get(f"/workspaces/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Workspace not found"}


def test_invalid_workspace_id(client):
    assert client.get("/workspaces/not-a-uuid").status_code == 422


def test_migration_round_trip(database):
    url, config = database
    command.check(config)
    command.downgrade(config, "base")
    engine = create_engine(url)
    try:
        assert "workspaces" not in inspect(engine).get_table_names()
        command.upgrade(config, "head")
        assert "workspaces" in inspect(engine).get_table_names()
        command.check(config)
    finally:
        engine.dispose()
