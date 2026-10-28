from types import SimpleNamespace
from uuid import uuid4
import pytest
from atlas.answers import get_answer_provider
from atlas.verification import get_claim_verifier
pytestmark = pytest.mark.database


def setup_memory(client):
    ws = client.post('/workspaces', json={'name': 'Memory'}).json()['id']
    base = f'/workspaces/{ws}'
    source = client.post(f'{base}/sources', files={'file': ('evidence.txt', 'Transactions use logs. Café 😀'.encode())}).json()['id']
    client.post(f'{base}/sources/{source}/passages')
    client.app.dependency_overrides[get_answer_provider] = lambda: SimpleNamespace(generate=lambda q, e: {
        'status': 'answered', 'claims': [{'text': 'Durability uses logs.', 'passage_ids': [e[0].id]}]})
    answer = client.post(f'{base}/answers', json={'question': 'transactions'}).json()
    return base, source, answer


def test_memory_interpretations_and_evidence_history_are_separate_and_idempotent(client):
    base, source, answer = setup_memory(client)
    url = f"{base}/answers/{answer['id']}/remember"
    first = client.post(url).json()
    assert first[0]['kind'] == 'generated_interpretation'
    assert first[0]['evidence'][0]['relation'] == 'mentions'
    assert client.post(url).json() == first
    class Verifier:
        identity = 'fake-supported'
        def verify(self, q, claims, citations):
            return {'judgments': [{'claim_index': 0, 'status': 'supported', 'passage_ids': claims[0].passage_ids, 'explanation': 'Fixture'}]}
    client.app.dependency_overrides[get_claim_verifier] = Verifier
    client.post(f"{base}/answers/{answer['id']}/verifications")
    later = client.post(url).json()
    assert later[0]['id'] == first[0]['id'] and len(later[0]['evidence']) == 2
    assert later[0]['evidence'][0] == first[0]['evidence'][0]
    assert later[0]['evidence'][1]['relation'] == 'supports'
    assert later[0]['evidence'][1]['snapshot']['text'] == 'Transactions use logs. Café 😀'
    assert client.get(f"{base}/answers/{answer['id']}").json() == answer
    assert client.get(f"{base}/claims/{first[0]['id']}").json() == later[0]
    assert client.get(f"/workspaces/{uuid4()}/claims/{first[0]['id']}").status_code == 404
