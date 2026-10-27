from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text

from atlas.main import create_app
from atlas.sources import MAX_REQUEST_BYTES, MAX_SOURCE_BYTES

pytestmark = pytest.mark.database


@pytest.fixture
def sources_url(client):
    response = client.post("/workspaces", json={"name": "Research"})
    assert response.status_code == 201
    return f'/workspaces/{response.json()["id"]}/sources'


def upload(client, url, content=b"Evidence", filename="notes.txt"):
    return client.post(url, files={"file": (filename, content, "text/plain")})


def test_source_survives_restart_with_exact_bytes(database):
    content = "\ufeffCafé 🔬\r\nOriginal spacing.  \n".encode()
    with TestClient(create_app(database[0])) as client:
        workspace_id = client.post("/workspaces", json={"name": "Research"}).json()["id"]
        sources_url = f"/workspaces/{workspace_id}/sources"
        response = upload(client, sources_url, content, "../notes.TXT")
        assert response.status_code == 201
        source = response.json()
    assert UUID(source["id"]).version == 4
    assert source["workspace_id"] == sources_url.split("/")[2]
    assert source["title"] == "notes.TXT"
    assert source["content_hash"] == sha256(content).hexdigest()
    assert datetime.fromisoformat(source["created_at"]).tzinfo is not None
    with TestClient(create_app(database[0])) as restarted:
        assert restarted.get(sources_url).json() == [source]
        assert restarted.get(f'{sources_url}/{source["id"]}').json() == source
        response = restarted.get(f'{sources_url}/{source["id"]}/content')
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"
        assert response.content == content


def test_workspace_isolation_and_pagination(client, sources_url):
    first = upload(client, sources_url).json()
    second = upload(client, sources_url).json()
    assert first["id"] != second["id"]
    assert first["content_hash"] == second["content_hash"]
    listed = client.get(sources_url).json()
    assert len(listed) == 2
    assert client.get(sources_url, params={"limit": 1, "offset": 1}).json() == listed[1:]
    other_id = client.post("/workspaces", json={"name": "Other"}).json()["id"]
    other_url = f"/workspaces/{other_id}/sources"
    assert client.get(other_url).json() == []
    for suffix in ["", "/content"]:
        assert client.get(f'{other_url}/{first["id"]}{suffix}').status_code == 404
        assert client.get(f'{sources_url}/{uuid4()}{suffix}').status_code == 404


@pytest.mark.parametrize("content,filename,status", [
    (b"", "empty.txt", 422), (b" \r\n\t", "blank.txt", 422),
    (b"\xef\xbb\xbf", "bom.txt", 422), (b"\xff", "bad.txt", 422),
    (b"a\x00b", "nul.txt", 422), (b"text", "notes.pdf", 422),
    (b"text", "a" * 197 + ".txt", 422),
    (b"a" * (MAX_SOURCE_BYTES + 1), "large.txt", 413),
])
def test_invalid_upload_not_saved(client, sources_url, content, filename, status):
    assert upload(client, sources_url, content, filename).status_code == status
    assert client.get(sources_url).json() == []


def test_size_boundary_and_request_limit(client, sources_url):
    response = upload(client, sources_url, b"a" * MAX_SOURCE_BYTES, "a" * 196 + ".txt")
    assert response.status_code == 201
    assert len(response.json()["title"]) == 200
    # Chunked input has no Content-Length; the pre-parser limit must still apply.
    response = client.post(sources_url, content=iter([b"a" * 65536] * 18))
    assert 18 * 65536 > MAX_REQUEST_BYTES
    assert response.status_code == 413
    assert len(client.get(sources_url).json()) == 1


def test_missing_workspace_and_invalid_request(client, sources_url):
    missing = f"/workspaces/{uuid4()}/sources"
    assert upload(client, missing).status_code == 404
    assert client.get(missing).status_code == 404
    assert client.post(sources_url).status_code == 422
    assert client.get(sources_url, params={"limit": 101}).status_code == 422
    assert client.get(sources_url, params={"offset": -1}).status_code == 422
    assert client.get(f"{sources_url}/invalid-id").status_code == 422


def test_source_migration_preserves_workspaces(client, database, sources_url):
    _, config = database
    command.downgrade(config, "0001")
    command.upgrade(config, "head")
    assert client.get(sources_url).json() == []
    source = upload(client, sources_url).json()
    with client.app.state.engine.connect() as connection:
        row = connection.execute(
            text("SELECT title, content, content_hash FROM sources WHERE id = :id"),
            {"id": UUID(source["id"])},
        ).one()
    assert tuple(row) == ("notes.txt", "Evidence", sha256(b"Evidence").hexdigest())
