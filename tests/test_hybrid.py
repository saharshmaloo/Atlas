from types import SimpleNamespace
import pytest
from atlas.hybrid import get_embedding_factory, rank_fusion
from atlas.embeddings import get_embedding_provider
from atlas.answers import get_answer_provider
from tests.test_vector_search import SemanticFake
pytestmark = pytest.mark.database


def test_hybrid_recovers_synonyms_and_answer_context_without_changing_keyword_default(client):
    ws = client.post('/workspaces', json={'name': 'Hybrid'}).json()['id']
    base = f'/workspaces/{ws}'
    source = client.post(f'{base}/sources', files={'file': ('cats.txt', b'Cats rest.')}).json()['id']
    client.post(f'{base}/sources/{source}/passages')
    client.app.dependency_overrides[get_embedding_provider] = SemanticFake
    client.app.dependency_overrides[get_embedding_factory] = lambda: SemanticFake
    client.post(f'{base}/embeddings')
    assert client.get(f'{base}/search', params={'q': 'feline'}).json() == []
    results = client.get(f'{base}/hybrid-search', params={'q': 'feline'}).json()
    assert results['retrieval'] == 'hybrid-rrf60-v1' and results['results'][0]['text'] == 'Cats rest.'
    client.app.dependency_overrides[get_answer_provider] = lambda: SimpleNamespace(generate=lambda q, e: {
        'status': 'answered', 'claims': [{'text': 'Cats rest.', 'passage_ids': [e[0].id]}]})
    assert client.post(f'{base}/answers', json={'question': 'feline'}).json()['status'] == 'insufficient_evidence'
    answer = client.post(f'{base}/answers', json={'question': 'feline', 'retrieval': 'hybrid'}, headers={'Idempotency-Key': 'hybrid'})
    assert answer.json()['status'] == 'answered'
    assert answer.json()['provenance']['retrieval'] == 'hybrid-rrf60-v1'
    assert client.post(f'{base}/answers', json={'question': 'feline'}, headers={'Idempotency-Key': 'hybrid'}).status_code == 409
    def unavailable():
        from fastapi import HTTPException
        raise HTTPException(503, 'unavailable')
    client.app.dependency_overrides[get_embedding_factory] = lambda: unavailable
    assert client.get(f'{base}/hybrid-search', params={'q': 'cats'}).json()['retrieval'] == 'keyword-fallback-v1'


def test_rank_fusion_deduplicates_and_rewards_shared_evidence():
    class Item(SimpleNamespace):
        def model_copy(self, update): return Item(**{**vars(self), **update})
    a = Item(id='a', source_id='s', position=0)
    b = Item(id='b', source_id='s', position=1)
    result = rank_fusion([[a, b], [b, b]], 10)
    assert [item.id for item in result] == ['b', 'a']
    assert result[0].score == 1/62 + 1/61
