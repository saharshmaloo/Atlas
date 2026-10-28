from uuid import uuid4
import pytest
from atlas.verification import get_claim_verifier

pytestmark = pytest.mark.database


def test_verification_is_persisted_separately_and_workspace_scoped(client):
    ws = client.post('/workspaces', json={'name': 'Judgments'}).json()['id']
    base = f'/workspaces/{ws}/answers'
    saved = client.post(base, json={'question': 'No evidence'}).json()
    url = f"{base}/{saved['id']}/verifications"
    assert client.get(url).json() == []
    response = client.post(url)
    assert response.status_code == 201
    assert response.json()['judgments'] == []
    assert client.get(url).json() == [response.json()]
    assert client.get(f"{base}/{saved['id']}").json() == saved
    other = client.post('/workspaces', json={'name': 'Other'}).json()['id']
    assert client.post(url.replace(ws, other)).status_code == 404
    assert client.get(url.replace(saved['id'], str(uuid4()))).status_code == 404
    class BadVerifier:
        identity = 'bad'
        def verify(self, *args):
            return {'judgments': [{'claim_index': 0, 'status': 'unsupported', 'passage_ids': [], 'explanation': 'Invalid'}]}
    client.app.dependency_overrides[get_claim_verifier] = BadVerifier
    assert client.post(url).status_code == 502
    assert len(client.get(url).json()) == 1
