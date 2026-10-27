from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from atlas.main import create_app

pytestmark = pytest.mark.database


@pytest.fixture
def workspace(client):
    response = client.post("/workspaces", json={"name": "Search research"})
    assert response.status_code == 201
    return response.json()["id"]


def add_source(client, workspace, title, content, generate=True):
    response = client.post(
        f"/workspaces/{workspace}/sources",
        files={"file": (title, content.encode(), "text/plain")},
    )
    assert response.status_code == 201
    source_id = response.json()["id"]
    if generate:
        assert client.post(f"/workspaces/{workspace}/sources/{source_id}/passages").status_code == 200
    return source_id


def search(client, workspace, query, **params):
    return client.get(f"/workspaces/{workspace}/search", params={"q": query, **params})


def test_ranked_results_include_exact_citation_metadata(client, workspace):
    content = "\ufeffDistributed transactions. Distributed transactions. Distributed transactions."
    relevant = add_source(client, workspace, "transactions.txt", content)
    weaker = add_source(client, workspace, "overview.txt", "Distributed transactions involve networks.")
    add_source(client, workspace, "unrelated.txt", "The ocean contains many fish.")
    response = search(client, workspace, "distributed transactions")
    assert response.status_code == 200
    results = response.json()
    assert [row["source_id"] for row in results] == [relevant, weaker]
    assert results[0]["score"] > results[1]["score"] > 0
    first = results[0]
    assert first["source_title"] == "transactions.txt"
    assert UUID(first["id"]).version == 5
    assert first["position"] == 0
    assert first["chunker_version"] == "paragraph-v1"
    assert first["text"] == content[first["start_char"]:first["end_char"]]
    assert search(client, workspace, "distributed transactions", limit=1).json() == results[:1]


def test_stemming_phrases_or_and_exclusion(client, workspace):
    adjacent = add_source(client, workspace, "adjacent.txt", "Databases support distributed transactions.")
    separated = add_source(client, workspace, "separated.txt", "Distributed systems coordinate transactions.")
    ocean = add_source(client, workspace, "ocean.txt", "Ocean habitats support fish.")
    assert [r["source_id"] for r in search(client, workspace, "database").json()] == [adjacent]
    assert [r["source_id"] for r in search(client, workspace, '"distributed transactions"').json()] == [adjacent]
    assert {r["source_id"] for r in search(client, workspace, "database OR ocean").json()} == {adjacent, ocean}
    assert [r["source_id"] for r in search(client, workspace, "distributed -database").json()] == [separated]


def test_empty_results_isolation_and_ungenerated_sources(client, workspace):
    add_source(client, workspace, "unprocessed.txt", "secret quasar", generate=False)
    other = client.post("/workspaces", json={"name": "Other"}).json()["id"]
    add_source(client, other, "private.txt", "secret quasar")
    for query in ["secret", "quasar", "the and", "!!!", "missingword"]:
        assert search(client, workspace, query).json() == []
    assert search(client, other, "quasar").json()
    assert search(client, str(uuid4()), "quasar").status_code == 404


@pytest.mark.parametrize("params", [
    {}, {"q": ""}, {"q": " \t\n"}, {"q": "a" * 501}, {"q": "a\x00b"},
    {"q": "test", "limit": 0}, {"q": "test", "limit": 51}, {"q": "test", "limit": "bad"},
])
def test_invalid_search_parameters(client, workspace, params):
    assert client.get(f"/workspaces/{workspace}/search", params=params).status_code == 422


def test_tied_scores_have_stable_order_and_query_text_is_bound(client, workspace):
    for _ in range(3):
        add_source(client, workspace, "same.txt", "transaction evidence")
    results = search(client, workspace, "transaction").json()
    assert len(results) == 3
    assert len({r["score"] for r in results}) == 1
    assert [r["source_id"] for r in results] == sorted(r["source_id"] for r in results)
    assert search(client, workspace, "transaction").json() == results
    response = search(client, workspace, "'; DROP TABLE workspaces; --")
    assert response.status_code == 200
    assert client.get(f"/workspaces/{workspace}").status_code == 200
    assert search(client, workspace, "transaction").json() == results


def test_migration_indexes_existing_passages_and_search_survives_restart(client, database, workspace):
    # Create passages on the previous schema, then test backfill through upgrade.
    command.downgrade(database[1], "0003")
    with client.app.state.engine.begin() as connection:
        connection.exec_driver_sql("""
            INSERT INTO sources (id, workspace_id, title, content, content_hash)
            VALUES ('00000000-0000-0000-0000-000000000001', %s, 'old.txt', 'quasar evidence', repeat('a', 64))
        """, (UUID(workspace),))
        connection.exec_driver_sql("""
            INSERT INTO passages (id, source_id, position, start_char, end_char, text, chunker_version)
            VALUES ('00000000-0000-0000-0000-000000000002',
                    '00000000-0000-0000-0000-000000000001', 0, 0, 15, 'quasar evidence', 'paragraph-v1')
        """)
    command.upgrade(database[1], "head")
    results = search(client, workspace, "quasar").json()
    assert len(results) == 1
    assert results[0]["text"] == "quasar evidence"
    indexes = inspect(client.app.state.engine).get_indexes("passages")
    index = next(index for index in indexes if index["name"] == "ix_passages_search_vector")
    assert index["dialect_options"]["postgresql_using"] == "gin"
    with TestClient(create_app(database[0])) as restarted:
        assert search(restarted, workspace, "quasar").json() == results
    command.check(database[1])
