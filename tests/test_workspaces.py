from datetime import datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from atlas.main import create_app
from atlas.workspaces import Workspace

pytestmark = pytest.mark.database


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
        assert not {"workspaces", "sources", "passages", "answers"} & set(inspect(engine).get_table_names())
        command.upgrade(config, "head")
        assert {"workspaces", "sources", "passages", "answers"} <= set(inspect(engine).get_table_names())
        command.check(config)
    finally:
        engine.dispose()
