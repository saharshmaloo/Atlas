from types import SimpleNamespace
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from atlas.embeddings import EmbeddingError, EmbeddingSpec, PassageEmbedding, embed_batch, store_vectors

SPEC = EmbeddingSpec(provider='fake', model='fixed', version='1', dimensions=2)


@pytest.mark.parametrize('vector', [[0, 0], [float('nan'), 1], [1], [True, 2], [float('inf'), 1]])
def test_rejects_bad_vectors(vector):
    with pytest.raises(EmbeddingError): embed_batch(SimpleNamespace(spec=SPEC, embed=lambda texts: [vector]), ['evidence'])


def test_normalizes_and_bounds_batches():
    provider = SimpleNamespace(spec=SPEC, embed=lambda texts: [[3, 4]] * len(texts))
    assert embed_batch(provider, ['evidence']) == [[.6, .8]]
    for texts in [[], ['a'] * 17, ['x' * 1001]]:
        with pytest.raises(EmbeddingError): embed_batch(provider, texts)
    provider.embed = lambda texts: []
    with pytest.raises(EmbeddingError): embed_batch(provider, ['evidence'])


@pytest.mark.database
def test_embedding_versions_persist_without_replacing_old_vectors(client):
    ws = client.post('/workspaces', json={'name': 'Embeddings'}).json()['id']
    url = f'/workspaces/{ws}/sources'
    source = client.post(url, files={'file': ('a.txt', b'evidence')}).json()['id']
    client.post(f'{url}/{source}/passages')
    from uuid import UUID
    pid = UUID(client.get(f'{url}/{source}/passages').json()[0]['id'])
    with Session(client.app.state.engine) as session:
        store_vectors(session, SPEC, [pid], [[3, 4]])
        store_vectors(session, SPEC, [pid], [[1, 0]])
        store_vectors(session, SPEC.model_copy(update={'version': '2'}), [pid], [[1, 0]])
        session.commit()
    with Session(client.app.state.engine) as session:
        rows = list(session.scalars(select(PassageEmbedding)))
        assert len(rows) == 2
        assert session.get(PassageEmbedding, (pid, SPEC.id)).vector == [.6, .8]
