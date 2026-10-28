import re
import pytest
from atlas.embeddings import EmbeddingSpec, get_embedding_provider
pytestmark = pytest.mark.database


class SemanticFake:
    spec = EmbeddingSpec(provider='fake', model='semantic', version='1', dimensions=2)
    def embed(self, texts):
        return [[1, 0] if bool(set(re.findall(r'\w+', text.lower())) & {'cat', 'cats', 'feline'}) else [0, 1] for text in texts]


def test_vector_retrieval_profiles_scoping_and_citation_contract(client):
    ws = client.post('/workspaces', json={'name': 'Semantic'}).json()['id']
    base = f'/workspaces/{ws}'
    client.app.dependency_overrides[get_embedding_provider] = SemanticFake
    for name in ['Cats rest.', 'Databases replicate.']:
        source = client.post(f'{base}/sources', files={'file': (f'{name}.txt', name.encode())}).json()['id']
        client.post(f'{base}/sources/{source}/passages')
    assert client.post(f'{base}/embeddings').json()['complete']
    results = client.get(f'{base}/vector-search', params={'q': 'feline', 'limit': 2}).json()
    assert results[0]['text'] == 'Cats rest.' and results[0]['score'] == 1
    assert results[1]['score'] == 0
    assert results[0]['end_char'] - results[0]['start_char'] == len(results[0]['text'])
    assert client.get(f'{base}/vector-search', params={'q': 'feline', 'limit': 2}).json() == results
    other = client.post('/workspaces', json={'name': 'Other'}).json()['id']
    assert client.get(f'/workspaces/{other}/vector-search', params={'q': 'feline'}).json() == []
    class NewVersion(SemanticFake):
        spec = SemanticFake.spec.model_copy(update={'version': '2'})
    client.app.dependency_overrides[get_embedding_provider] = NewVersion
    assert client.get(f'{base}/vector-search', params={'q': 'feline'}).json() == []
    assert client.get(f'{base}/vector-search', params={'q': '  '}).status_code == 422
