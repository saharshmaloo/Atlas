from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
from atlas.answers import ProviderTimeout, get_answer_provider

pytestmark = pytest.mark.database


def setup(client):
    workspace = client.post('/workspaces', json={'name': 'Retry'}).json()['id']
    base = f'/workspaces/{workspace}'
    source = client.post(f'{base}/sources', files={'file': ('a.txt', b'transactions')}).json()['id']
    client.post(f'{base}/sources/{source}/passages')
    return base


def test_concurrent_retries_share_one_saved_answer(client):
    base = setup(client)
    entered, release = threading.Event(), threading.Event()
    calls = []
    class Provider:
        def generate(self, question, evidence):
            calls.append(question); entered.set()
            assert release.wait(5)
            return {'status': 'answered', 'claims': [{'text': 'Transactions', 'passage_ids': [evidence[0].id]}]}
    client.app.dependency_overrides[get_answer_provider] = Provider
    def submit(question='transactions'):
        return client.post(f'{base}/answers', json={'question': question}, headers={'Idempotency-Key': 'retry-1'})
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(submit)
        assert entered.wait(5)
        second = pool.submit(submit)
        release.set()
        a, b = first.result(), second.result()
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    assert calls == ['transactions']
    assert submit('another question').status_code == 409
    assert len(client.get(f'{base}/answers').json()) == 1
    assert submit('  transactions  ').json() == a.json()


def test_failed_key_can_retry_and_keys_are_workspace_scoped(client):
    base = setup(client)
    class Provider:
        def generate(self, *args):
            raise ProviderTimeout()
    client.app.dependency_overrides[get_answer_provider] = Provider
    headers = {'Idempotency-Key': 'same'}
    assert client.post(f'{base}/answers', json={'question': 'transactions'}, headers=headers).status_code == 504
    assert client.get(f'{base}/answers').json() == []
    first = client.post(f'{base}/answers', json={'question': 'unmatched'}, headers=headers).json()
    other = setup(client)
    second = client.post(f'{other}/answers', json={'question': 'unmatched'}, headers=headers).json()
    assert first['id'] != second['id']
