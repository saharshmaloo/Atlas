import pytest
from atlas.embeddings import EmbeddingError, EmbeddingSpec, get_embedding_provider
pytestmark = pytest.mark.database


class FakeEmbeddingProvider:
    spec = EmbeddingSpec(provider='fake', model='fixed', version='1', dimensions=2)
    calls = 0
    fail_on = None
    def embed(self, texts):
        self.calls += 1
        if self.calls == self.fail_on: raise EmbeddingError('secret')
        return [[1, 0] for text in texts]


def setup_embeddings(client, text='transactions ' + 'x' * 3000):
    ws = client.post('/workspaces', json={'name': 'Vectors'}).json()['id']
    base = f'/workspaces/{ws}'
    source = client.post(f'{base}/sources', files={'file': ('a.txt', text.encode())}).json()['id']
    client.post(f'{base}/sources/{source}/passages')
    fake = FakeEmbeddingProvider()
    client.app.dependency_overrides[get_embedding_provider] = lambda: fake
    return base, fake


def test_batches_resume_after_partial_failure_without_duplicate_provider_calls(client):
    base, provider = setup_embeddings(client)
    provider.fail_on = 2
    response = client.post(f'{base}/embeddings?batch_size=2&max_batches=2')
    assert response.status_code == 502 and 'secret' not in response.text
    status = client.get(f'{base}/embeddings/{provider.spec.id}').json()
    assert status['embedded'] == 2 and status['remaining'] == 2
    provider.fail_on = None
    status = client.post(f'{base}/embeddings?batch_size=2&max_batches=2').json()
    assert status['complete'] and status['embedded'] == 4
    calls = provider.calls
    assert client.post(f'{base}/embeddings').json()['complete']
    assert provider.calls == calls
    other, _ = setup_embeddings(client, 'other')
    assert client.get(f'{other}/embeddings/{provider.spec.id}').json()['embedded'] == 0
    assert client.post(f'{base}/embeddings?batch_size=17').status_code == 422
