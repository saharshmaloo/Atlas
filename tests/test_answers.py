import json
from uuid import uuid4

import httpx
import pytest
from openai import OpenAI

from atlas import answers


class FakeProvider:
    def __init__(self):
        self.calls = []
        self.result = None

    def generate(self, question, evidence):
        self.calls.append((question, evidence))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result if self.result is not None else {
            "status": "answered", "claims": [{
                "text": "Transactions use a replicated log.", "passage_ids": [str(evidence[0].id)],
            }],
        }


def add_source(client, workspace, text):
    source = client.post(f"/workspaces/{workspace}/sources", files={
        "file": ("notes.txt", text.encode(), "text/plain"),
    }).json()["id"]
    url = f"/workspaces/{workspace}/sources/{source}/passages"
    assert client.post(url).status_code == 200
    return client.get(url).json()


@pytest.fixture
def setup_answer(client):
    workspace = client.post("/workspaces", json={"name": "Research"}).json()["id"]
    add_source(client, workspace, "Transactions use a replicated log.")
    fake = FakeProvider()
    client.app.dependency_overrides[answers.get_answer_provider] = lambda: fake
    return f"/workspaces/{workspace}/answers", workspace, fake


@pytest.mark.database
def test_answer_uses_retrieved_evidence_and_returns_citation_metadata(client, setup_answer):
    url, _, fake = setup_answer
    other = client.post("/workspaces", json={"name": "Other"}).json()["id"]
    foreign = add_source(client, other, "Transactions contain secret outside evidence.")[0]
    response = client.post(url, json={"question": "  How do transactions work?  "})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "answered"
    assert result["answer"] == result["claims"][0]["text"]
    citation = result["citations"][0]
    assert result["claims"][0]["passage_ids"] == [citation["id"]]
    assert citation["source_title"] == "notes.txt"
    assert citation["text"] == "Transactions use a replicated log."
    assert citation["end_char"] - citation["start_char"] == len(citation["text"])
    assert fake.calls[0][0] == "How do transactions work?"
    assert all(str(item.id) != foreign["id"] for item in fake.calls[0][1])
    fake.result = {"status": "answered", "claims": [{"text": "Leaked.", "passage_ids": [foreign["id"]]}]}
    assert client.post(url, json={"question": "transactions"}).status_code == 502


@pytest.mark.database
def test_no_matches_skips_provider_and_model_can_abstain(client, setup_answer):
    url, _, fake = setup_answer
    for question in ["quasar", "the and", "!!!"]:
        response = client.post(url, json={"question": question})
        assert response.status_code == 200
        assert response.json()["status"] == "insufficient_evidence"
        assert response.json()["claims"] == response.json()["citations"] == []
    assert not fake.calls
    fake.result = {"status": "insufficient_evidence", "claims": []}
    assert client.post(url, json={"question": "transactions"}).json()["status"] == "insufficient_evidence"


@pytest.mark.database
@pytest.mark.parametrize("result", [
    {"status": "answered", "claims": []},
    {"status": "answered", "claims": [{"text": "No citation", "passage_ids": []}]},
    {"status": "answered", "claims": [{"text": "Unknown", "passage_ids": [str(uuid4())]}]},
    {"status": "answered", "claims": [{"text": " ", "passage_ids": [str(uuid4())]}]},
    {"status": "insufficient_evidence", "claims": [{"text": "Contradiction", "passage_ids": [str(uuid4())]}]},
    {"bad": "schema"},
])
def test_rejects_invalid_provider_output(client, setup_answer, result):
    url, _, fake = setup_answer
    fake.result = result
    assert client.post(url, json={"question": "transactions"}).status_code == 502


@pytest.mark.database
@pytest.mark.parametrize("error,status", [
    (answers.ProviderUnavailable("secret"), 503), (answers.ProviderFailure("secret"), 502),
    (answers.ProviderTimeout("secret"), 504),
])
def test_provider_errors_are_sanitized(client, setup_answer, error, status):
    url, _, fake = setup_answer
    fake.result = error
    response = client.post(url, json={"question": "transactions"})
    assert response.status_code == status
    assert "secret" not in response.text


@pytest.mark.database
@pytest.mark.parametrize("body", [{}, {"question": ""}, {"question": " \n"}, {"question": "x" * 501}, {"question": "a\x00b"}, {"question": 1}])
def test_question_validation(client, setup_answer, body):
    url, _, fake = setup_answer
    assert client.post(url, json=body).status_code == 422
    assert not fake.calls


@pytest.mark.database
def test_missing_workspace_and_bounded_context(client, setup_answer):
    url, workspace, fake = setup_answer
    assert client.post(f"/workspaces/{uuid4()}/answers", json={"question": "transactions"}).status_code == 404
    assert not fake.calls
    add_source(client, workspace, ("transactions " + "\x01" * 987) * 8)
    assert client.post(url, json={"question": "transactions"}).status_code == 200
    question, evidence = fake.calls[0]
    assert 0 < len(evidence) < answers.MAX_EVIDENCE_PASSAGES
    assert len(answers.context_json(question, evidence)) <= answers.MAX_CONTEXT_CHARS


@pytest.mark.database
def test_missing_provider_configuration(client, setup_answer, monkeypatch):
    url, _, _ = setup_answer
    client.app.dependency_overrides.clear()
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    assert client.post(url, json={"question": "transactions"}).status_code == 503


@pytest.mark.parametrize("mode,error", [
    ("ok", None), ("http_error", answers.ProviderFailure), ("timeout", answers.ProviderTimeout),
    ("refusal", answers.ProviderFailure), ("incomplete", answers.ProviderFailure),
    ("malformed", answers.ProviderFailure),
])
def test_openai_adapter_with_real_sdk_and_mock_http(monkeypatch, mode, error):
    requests = []

    def respond(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.url.path == "/v1/responses"
        assert payload["store"] is False
        assert payload["max_output_tokens"] == 1600
        assert payload["text"]["format"]["type"] == "json_schema"
        assert "untrusted" in payload["instructions"]
        if mode == "timeout":
            raise httpx.ReadTimeout("private provider details", request=request)
        if mode == "http_error":
            return httpx.Response(503, json={"error": {"message": "private provider details"}})
        content = [{"type": "output_text", "text": json.dumps({"status": "insufficient_evidence", "claims": []}), "annotations": []}]
        if mode == "malformed":
            content[0]["text"] = "not JSON"
        if mode == "refusal":
            content = [{"type": "refusal", "refusal": "Cannot answer"}]
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 0, "model": "test-model",
            "status": "incomplete" if mode == "incomplete" else "completed",
            "output": [{"id": "msg_test", "type": "message", "role": "assistant", "status": "completed", "content": content}],
        })

    def sdk(**kwargs):
        assert kwargs["timeout"] == 30 and kwargs["max_retries"] == 0
        return OpenAI(http_client=httpx.Client(transport=httpx.MockTransport(respond)), **kwargs)

    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setattr(answers, "OpenAI", sdk)
    if error:
        with pytest.raises(error):
            answers.OpenAIAnswerProvider().generate("question", [])
    else:
        assert answers.OpenAIAnswerProvider().generate("question", []).status == "insufficient_evidence"
    assert len(requests) == 1
