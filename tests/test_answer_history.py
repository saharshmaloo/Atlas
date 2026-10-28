from datetime import datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from atlas.answers import ProviderFailure, get_answer_provider
from atlas.main import create_app

pytestmark = pytest.mark.database


def setup_history(client):
    workspace = client.post("/workspaces", json={"name": "History"}).json()["id"]
    source = client.post(f"/workspaces/{workspace}/sources", files={
        "file": ("evidence.txt", "Transactions use a replicated log. Café 🔬".encode(), "text/plain"),
    }).json()["id"]
    assert client.post(f"/workspaces/{workspace}/sources/{source}/passages").status_code == 200
    calls = []

    def generate(question, evidence):
        calls.append(question)
        return {"status": "answered", "claims": [{
            "text": "Transactions use a replicated log. Café 🔬", "passage_ids": [str(evidence[0].id)],
        }]}

    provider = SimpleNamespace(generate=generate)
    client.app.dependency_overrides[get_answer_provider] = lambda: provider
    return f"/workspaces/{workspace}/answers", calls, provider


@pytest.fixture
def history(client):
    return setup_history(client)


def test_saved_answer_survives_restart_without_provider(database):
    with TestClient(create_app(database[0])) as client:
        url, calls, _ = setup_history(client)
        response = client.post(url, json={"question": "  How do transactions work?  "})
        assert response.status_code == 200
        saved = response.json()
        assert UUID(saved["id"]).version == 4
        assert saved["question"] == "How do transactions work?"
        assert datetime.fromisoformat(saved["created_at"]).tzinfo is not None
        assert len(calls) == 1
    with TestClient(create_app(database[0])) as restarted:
        response = restarted.get(f'{url}/{saved["id"]}')
        assert response.status_code == 200
        assert response.json() == saved
        summary = restarted.get(url).json()[0]
        assert summary == {key: saved[key] for key in ["id", "workspace_id", "question", "created_at", "status"]}


def test_citation_snapshots_do_not_change_with_source_metadata(client, history):
    url, calls, _ = history
    saved = client.post(url, json={"question": "transactions"}).json()
    source_id = UUID(saved["citations"][0]["source_id"])
    with client.app.state.engine.begin() as connection:
        connection.execute(text("UPDATE sources SET title = 'renamed.txt' WHERE id = :id"), {"id": source_id})
    assert client.get(f'{url}/{saved["id"]}').json() == saved
    assert saved["citations"][0]["source_title"] == "evidence.txt"
    assert len(calls) == 1


def test_pagination_and_repeated_questions_create_distinct_records(client, history):
    url, _, _ = history
    records = [client.post(url, json={"question": "transactions"}).json() for _ in range(3)]
    assert len({record["id"] for record in records}) == 3
    expected = sorted(records, key=lambda record: (record["created_at"], record["id"]), reverse=True)
    listed = client.get(url).json()
    assert [row["id"] for row in listed] == [row["id"] for row in expected]
    assert client.get(url, params={"limit": 1, "offset": 1}).json() == listed[1:2]
    for params in [{"limit": 0}, {"limit": 101}, {"offset": -1}]:
        assert client.get(url, params=params).status_code == 422


def test_insufficient_evidence_is_saved(client, history):
    url, calls, provider = history
    no_matches = client.post(url, json={"question": "quasar"}).json()
    assert no_matches["status"] == "insufficient_evidence"
    assert not calls
    provider.generate = lambda *_: {"status": "insufficient_evidence", "claims": []}
    abstained = client.post(url, json={"question": "transactions"}).json()
    assert abstained["status"] == "insufficient_evidence"
    for result in [no_matches, abstained]:
        assert client.get(f'{url}/{result["id"]}').json() == result
        assert result["claims"] == result["citations"] == []


@pytest.mark.parametrize("failure", ["provider", "citation", "nul"])
def test_failed_generation_does_not_create_history(client, history, failure):
    url, _, provider = history

    def generate(*_):
        if failure == "provider":
            raise ProviderFailure
        return {"status": "answered", "claims": [{
            "text": "bad\x00text" if failure == "nul" else "invalid citation",
            "passage_ids": [str(uuid4())],
        }]}

    provider.generate = generate
    assert client.post(url, json={"question": "transactions"}).status_code == 502
    assert client.get(url).json() == []


def test_history_is_workspace_scoped_and_unknown_ids_return_404(client, history):
    url, _, _ = history
    saved = client.post(url, json={"question": "transactions"}).json()
    other = client.post("/workspaces", json={"name": "Other"}).json()["id"]
    other_url = f"/workspaces/{other}/answers"
    assert client.get(other_url).json() == []
    assert client.get(f'{other_url}/{saved["id"]}').status_code == 404
    assert client.get(f"{url}/{uuid4()}").status_code == 404
    assert client.get(f"{url}/bad-id").status_code == 422
    assert client.get(f"/workspaces/{uuid4()}/answers").status_code == 404


def test_history_migration_preserves_sources(client, database, history):
    url, _, _ = history
    assert client.post(url, json={"question": "transactions"}).status_code == 200
    command.downgrade(database[1], "0004")
    assert "answers" not in inspect(client.app.state.engine).get_table_names()
    command.upgrade(database[1], "head")
    assert client.get(url).json() == []
    assert client.post(url, json={"question": "transactions"}).status_code == 200
    command.check(database[1])
