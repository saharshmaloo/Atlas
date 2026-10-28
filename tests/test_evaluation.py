import json
from pathlib import Path

import pytest

from atlas.evaluation import retrieval_metrics

CORPUS = Path(__file__).resolve().parents[1] / 'benchmarks/retrieval-v1.json'


def test_retrieval_metrics_penalize_missing_and_misranked_evidence():
    result = retrieval_metrics([(['wrong', 'right', 'right'], ['right', 'missing']), ([], [])])
    assert result['recall'] == .5
    assert result['mrr'] == .5
    assert result['ndcg'] < .5
    assert result['empty_query_accuracy'] == 1
    assert retrieval_metrics([])['recall'] is None


@pytest.mark.database
def test_labeled_keyword_baseline(client):
    corpus = json.loads(CORPUS.read_text())
    workspace = client.post('/workspaces', json={'name': corpus['version']}).json()['id']
    base = f'/workspaces/{workspace}'
    titles = {}
    for name, content in corpus['sources'].items():
        source = client.post(f'{base}/sources', files={'file': (f'{name}.txt', content.encode())}).json()['id']
        assert client.post(f'{base}/sources/{source}/passages').status_code == 200
        titles[source] = name
    cases = []
    for case in corpus['queries']:
        response = client.get(f'{base}/search', params={'q': case['q'], 'limit': 5})
        assert response.status_code == 200
        cases.append(([titles[row['source_id']] for row in response.json()], case['relevant']))
    metrics = retrieval_metrics(cases)
    assert metrics == {'recall': .8, 'mrr': .8, 'ndcg': .8, 'empty_query_accuracy': 1.0}
