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


def test_grounding_metrics_distinguish_membership_from_support():
    from atlas.evaluation import grounding_metrics
    report = grounding_metrics([{'citations_valid': True, 'predicted_support': 'supported',
        'expected_support': 'unsupported', 'abstained': False, 'expected_abstain': True}])
    assert report == {'citation_membership': 1, 'support_accuracy': 0, 'false_support_rate': 1, 'abstention_accuracy': 0}


@pytest.mark.database
def test_grounding_and_abstention_baseline(client):
    from atlas.answers import get_answer_provider
    from atlas.evaluation import grounding_metrics
    corpus = json.loads((CORPUS.parent / 'grounding-v1.json').read_text())
    measured = []
    for case in corpus['cases']:
        workspace = client.post('/workspaces', json={'name': corpus['version']}).json()['id']
        base = f'/workspaces/{workspace}'
        source = client.post(f'{base}/sources', files={'file': ('case.txt', case['evidence'].encode())}).json()['id']
        client.post(f'{base}/sources/{source}/passages')
        class FixtureProvider:
            def generate(self, question, evidence):
                return {'status': 'answered', 'claims': [{'text': case['claim'], 'passage_ids': [evidence[0].id]}]}
        client.app.dependency_overrides[get_answer_provider] = FixtureProvider
        answer = client.post(f'{base}/answers', json={'question': case['question']}).json()
        response = client.post(f"{base}/answers/{answer['id']}/verifications")
        assert response.status_code == 201
        judgments = response.json()['judgments']
        allowed = {item['id'] for item in answer['citations']}
        measured.append({'citations_valid': all(set(c['passage_ids']) <= allowed for c in answer['claims']),
            'predicted_support': judgments[0]['status'] if judgments else None,
            'expected_support': case['support'], 'abstained': answer['status'] == 'insufficient_evidence',
            'expected_abstain': case['abstain']})
    assert grounding_metrics(measured) == {'citation_membership': 1, 'support_accuracy': 1/3,
                                         'false_support_rate': None, 'abstention_accuracy': 1}
