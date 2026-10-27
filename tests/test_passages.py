from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient

from atlas.main import create_app
from atlas.passages import MAX_PASSAGE_CHARS, passage_spans


@pytest.mark.parametrize("content", [
    "", "short", "a" * 1000, "a" * 1001, "a" * 3005,
    "\ufeffCafé 🔬e\u0301\r\n\r\n" * 200,
    "first\n\n" + "a" * 2500 + "\n\nlast  \n",
    "a\r\nb\n\nc\r\r" * 300,
    "\n \t\n" * 400 + "last",
])
def test_spans_cover_exact_source_without_gaps(content):
    spans = list(passage_spans(content))
    assert spans == list(passage_spans(content))
    assert "".join(content[start:end] for start, end in spans) == content
    previous = 0
    for start, end in spans:
        assert start == previous
        assert 0 < end - start <= MAX_PASSAGE_CHARS
        previous = end
    assert previous == len(content)


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_chunker_prefers_last_paragraph_boundary(newline):
    first = "a" * 400 + newline * 2 + "b" * 400 + newline * 2
    content = first + "c" * 400
    assert list(passage_spans(content)) == [(0, len(first)), (len(first), len(content))]


def test_single_newline_is_not_a_paragraph_boundary():
    assert list(passage_spans("a" * 998 + "\r\n" + "tail")) == [(0, 1000), (1000, 1004)]
    assert list(passage_spans("one\n\ntwo")) == [(0, 8)]


@pytest.fixture
def source(client):
    workspace = client.post("/workspaces", json={"name": "Research"}).json()["id"]
    content = "\ufeffCafé 🔬\r\n\r\n" + "a" * 2200 + "\n\nLast.  \n"
    response = client.post(
        f"/workspaces/{workspace}/sources",
        files={"file": ("notes.txt", content.encode(), "text/plain")},
    )
    assert response.status_code == 201
    source_id = response.json()["id"]
    return f"/workspaces/{workspace}/sources/{source_id}/passages", content, source_id


@pytest.mark.database
def test_generation_persistence_and_exact_offsets(database):
    # Close the original application and engine before retrieving the generated passages.
    with TestClient(create_app(database[0])) as client:
        workspace = client.post("/workspaces", json={"name": "Research"}).json()["id"]
        content = "\ufeffCafé 🔬e\u0301\r\n\r\n" + "long paragraph " * 200
        response = client.post(
            f"/workspaces/{workspace}/sources",
            files={"file": ("notes.txt", content.encode(), "text/plain")},
        )
        source_id = response.json()["id"]
        url = f"/workspaces/{workspace}/sources/{source_id}/passages"
        assert client.get(url).json() == []
        generated = client.post(url)
        assert generated.status_code == 200
        passages = client.get(url).json()
        assert generated.json() == {"source_id": source_id, "passage_count": len(passages)}
    with TestClient(create_app(database[0])) as restarted:
        assert restarted.get(url).json() == passages
        assert restarted.post(url).json() == generated.json()
        assert restarted.get(url).json() == passages
    assert "".join(p["text"] for p in passages) == content
    assert len({p["id"] for p in passages}) == len(passages)
    for position, passage in enumerate(passages):
        assert UUID(passage["id"]).version == 5
        assert passage["source_id"] == source_id
        assert passage["position"] == position
        assert passage["chunker_version"] == "paragraph-v1"
        assert passage["text"] == content[passage["start_char"]:passage["end_char"]]


@pytest.mark.database
def test_concurrent_generation_is_idempotent(client, source):
    url, content, _ = source
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.post(url), range(4)))
    assert all(response.status_code == 200 for response in responses)
    assert all(response.json() == responses[0].json() for response in responses)
    passages = client.get(url).json()
    assert len(passages) == responses[0].json()["passage_count"]
    assert "".join(p["text"] for p in passages) == content
    assert client.get(url, params={"limit": 1, "offset": 1}).json() == passages[1:2]


@pytest.mark.database
def test_isolation_missing_sources_and_invalid_queries(client, source):
    url, _, source_id = source
    workspace = client.post("/workspaces", json={"name": "Other"}).json()["id"]
    for inaccessible in [
        f"/workspaces/{workspace}/sources/{source_id}/passages",
        f"/workspaces/{uuid4()}/sources/{source_id}/passages",
        url.replace(source_id, str(uuid4())),
    ]:
        assert client.post(inaccessible).status_code == 404
        assert client.get(inaccessible).status_code == 404
    assert client.get(url).json() == []
    for params in [{"limit": 0}, {"limit": 101}, {"offset": -1}]:
        assert client.get(url, params=params).status_code == 422
    assert client.post(url.replace(source_id, "invalid")).status_code == 422


@pytest.mark.database
def test_migration_preserves_source_and_stable_ids(client, database, source):
    url, content, _ = source
    assert client.post(url).status_code == 200
    original = client.get(url).json()
    command.downgrade(database[1], "0002")
    command.upgrade(database[1], "head")
    assert client.get(url).json() == []
    assert client.get(url.removesuffix("/passages") + "/content").content == content.encode()
    assert client.post(url).status_code == 200
    assert client.get(url).json() == original
