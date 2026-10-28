import pytest
from sqlalchemy import text

from atlas.answers import get_answer_provider

pytestmark = pytest.mark.database


def test_provenance_persists_and_legacy_records_remain_readable(client):
    workspace = client.post('/workspaces', json={'name': 'Provenance'}).json()['id']
    base = f'/workspaces/{workspace}'
    source = client.post(f'{base}/sources', files={'file': ('a.txt', b'transactions')}).json()['id']
    client.post(f'{base}/sources/{source}/passages')
    class Provider:
        identity = {'provider': 'test', 'model': 'fixed-v1'}
        def generate(self, question, evidence):
            return {'status': 'answered', 'claims': [{'text': 'Transactions.', 'passage_ids': [evidence[0].id]}]}
    client.app.dependency_overrides[get_answer_provider] = Provider
    saved = client.post(f'{base}/answers', json={'question': 'transactions'}).json()
    provenance = saved['provenance']
    assert provenance['provider'] == 'test' and provenance['model'] == 'fixed-v1'
    assert provenance['retrieval'] == 'keyword-any-v1'
    assert provenance['prompt_version'] == 'evidence-v1'
    assert provenance['duration_ms'] >= 0
    assert client.get(f"{base}/answers/{saved['id']}").json() == saved
    absent = client.post(f'{base}/answers', json={'question': 'unmatched'}).json()
    assert absent['provenance']['provider'] is None
    with client.app.state.engine.begin() as connection:
        connection.execute(text("UPDATE answers SET response = response - 'provenance'"))
    assert client.get(f"{base}/answers/{saved['id']}").json()['provenance'] is None
