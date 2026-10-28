import pytest
from atlas.verification import get_claim_verifier
from tests.test_memory import setup_memory
pytestmark = pytest.mark.database


class SupportedVerifier:
    identity = 'fixture-supported'
    def verify(self, q, claims, citations):
        return {'judgments': [{'claim_index': i, 'status': 'supported', 'passage_ids': claim.passage_ids,
            'explanation': 'Fixture judgment'} for i, claim in enumerate(claims)]}


def test_memory_reuses_only_current_supported_original_evidence(client):
    base, source, answer = setup_memory(client)
    url = f"{base}/answers/{answer['id']}"
    client.post(f'{url}/remember')
    assert client.get(f'{base}/memory-search', params={'q': 'durability'}).json()[0]['kind'] == 'generated_interpretation'
    response = client.post(f'{base}/answers', json={'question': 'durability', 'use_memory': True}).json()
    assert response['status'] == 'insufficient_evidence'  # Uncertain memory cannot expand evidence.
    client.app.dependency_overrides[get_claim_verifier] = SupportedVerifier
    client.post(f'{url}/verifications'); client.post(f'{url}/remember')
    result = client.post(f'{base}/answers', json={'question': 'durability', 'use_memory': True}).json()
    assert result['status'] == 'answered' and result['provenance']['memory_passage_count'] == 1
    assert result['citations'][0]['text'] == 'Transactions use logs. Café 😀'
    assert result['citations'][0]['text'] != result['claims'][0]['text']
    client.post(f'{base}/sources/{source}/versions', files={'file': ('new.txt', b'Transactions changed.')})
    memory = client.get(f'{base}/memory-search', params={'q': 'durability'}).json()[0]
    assert all(edge['freshness'] == 'superseded_source' for edge in memory['evidence'])
    result = client.post(f'{base}/answers', json={'question': 'durability', 'use_memory': True}).json()
    assert result['status'] == 'insufficient_evidence'
    other = client.post('/workspaces', json={'name': 'Other'}).json()['id']
    assert client.get(f'/workspaces/{other}/memory-search', params={'q': 'durability'}).json() == []


def test_newer_verification_invalidates_older_supported_memory_even_if_remembered_late(client):
    base, _, answer = setup_memory(client)
    url = f"{base}/answers/{answer['id']}"
    client.app.dependency_overrides[get_claim_verifier] = SupportedVerifier
    supported = client.post(f'{url}/verifications').json()
    client.post(f'{url}/remember')
    assert client.post(f'{base}/answers', json={'question': 'durability', 'use_memory': True}).json()['status'] == 'answered'
    class Contradicted(SupportedVerifier):
        identity = 'newer-contradiction'
        def verify(self, *args):
            result = super().verify(*args)
            for judgment in result['judgments']: judgment['status'] = 'unsupported'
            return result
    client.app.dependency_overrides[get_claim_verifier] = Contradicted
    client.post(f'{url}/verifications')
    memory = client.get(f'{base}/memory-search?q=durability').json()[0]
    assert memory['state'] == 'assessment_outdated'
    # Explicitly re-saving an older assessment must not reinstate it for retrieval.
    client.post(f"{url}/remember?verification_id={supported['id']}")
    assert client.post(f'{base}/answers', json={'question': 'durability', 'use_memory': True}).json()['status'] == 'insufficient_evidence'
