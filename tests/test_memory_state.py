from uuid import uuid4
import pytest
from tests.test_memory import setup_memory
pytestmark = pytest.mark.database


def test_conflicts_and_supersession_retain_original_findings(client):
    base, _, first = setup_memory(client)
    a = client.post(f"{base}/answers/{first['id']}/remember").json()[0]
    second = client.post(f'{base}/answers', json={'question': 'transactions'}).json()
    b = client.post(f"{base}/answers/{second['id']}/remember").json()[0]
    relation = {'from_claim_id': a['id'], 'to_claim_id': b['id'], 'kind': 'contradicts', 'note': 'Explicit unresolved disagreement'}
    assert client.post(f'{base}/claim-relations', json=relation).status_code == 201
    assert client.get(f"{base}/claims/{a['id']}").json()['state'] == 'contested'
    relation.update(from_claim_id=b['id'], to_claim_id=a['id'], kind='supersedes', note='Newer interpretation')
    assert client.post(f'{base}/claim-relations', json=relation).status_code == 201
    old = client.get(f"{base}/claims/{a['id']}").json()
    assert old['state'] == 'superseded' and old['text'] == a['text'] and old['evidence'] == a['evidence']
    relation.update(from_claim_id=a['id'], to_claim_id=b['id'])
    assert client.post(f'{base}/claim-relations', json=relation).status_code == 409
    assert [item['id'] for item in client.get(f'{base}/memory-search?q=durability').json()] == [b['id']]
    relation['to_claim_id'] = str(uuid4())
    assert client.post(f'{base}/claim-relations', json=relation).status_code == 404


def test_open_question_updates_preserve_resolution_and_reopening_history(client):
    base, _, _ = setup_memory(client)
    question = client.post(f'{base}/questions', json={'question': 'What remains unknown?'}).json()
    assert question['status'] == 'open'
    url = f"{base}/questions/{question['id']}/updates"
    for status in ['resolved', 'open']:
        response = client.post(url, json={'status': status, 'note': f'Assessment: {status}'})
        assert response.status_code == 201 and response.json()['status'] == status
    result = client.get(f'{base}/questions').json()[0]
    assert len(result['updates']) == 2 and result['question'] == question['question']
    assert client.post(url.replace(base.split('/')[2], str(uuid4())), json={'status': 'resolved', 'note': 'Foreign'}).status_code == 404
