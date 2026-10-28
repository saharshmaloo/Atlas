"""Synthetic ablation: same tasks and providers with and without retained findings."""
import json
from pathlib import Path
import pytest
from atlas import answers
from atlas.answers import context_json, get_answer_provider
from atlas.verification import get_claim_verifier
from tests.test_memory_retrieval import SupportedVerifier
pytestmark = pytest.mark.database


def test_persistent_memory_ablation(client, monkeypatch):
    corpus = json.loads((Path(__file__).resolve().parents[1] / 'benchmarks/memory-v1.json').read_text())
    ws = client.post('/workspaces', json={'name': corpus['version']}).json()['id']
    base = f'/workspaces/{ws}'
    source = client.post(f'{base}/sources', files={'file': ('log.txt', corpus['source'].encode())}).json()['id']
    client.post(f'{base}/sources/{source}/passages')
    class FixtureProvider:
        calls = 0
        input_chars = 0
        def generate(self, question, evidence):
            self.calls += 1; self.input_chars += len(context_json(question, evidence))
            return {'status': 'answered', 'claims': [{'text': corpus['remembered_claim'], 'passage_ids': [evidence[0].id]}]}
    provider = FixtureProvider()
    client.app.dependency_overrides[get_answer_provider] = lambda: provider
    client.app.dependency_overrides[get_claim_verifier] = SupportedVerifier
    seed = client.post(f'{base}/answers', json={'question': corpus['seed_question']}).json()
    client.post(f"{base}/answers/{seed['id']}/verifications")
    client.post(f"{base}/answers/{seed['id']}/remember")
    original = answers.retrieve_passages
    retrievals = []
    def counted(*args):
        retrievals.append(args[2]); return original(*args)
    monkeypatch.setattr(answers, 'retrieve_passages', counted)
    report = {}
    for use_memory in [False, True]:
        initial_calls, initial_chars, initial_retrievals = provider.calls, provider.input_chars, len(retrievals)
        correct, durations = [], []
        for task in corpus['tasks']:
            response = client.post(f'{base}/answers', json={'question': task['question'], 'use_memory': use_memory})
            assert response.status_code == 200
            result = response.json()
            answered = result['status'] == 'answered'
            correct.append(answered == task['answerable'])
            if answered:
                assert result['claims'][0]['text'] == corpus['remembered_claim']
                assert result['citations'][0]['text'] == corpus['source']
                assert set(result['claims'][0]['passage_ids']) <= {c['id'] for c in result['citations']}
            durations.append(result['provenance']['duration_ms'])
        report['memory' if use_memory else 'baseline'] = {
            'fixture_quality_accuracy': sum(correct)/len(correct), 'keyword_retrievals': len(retrievals) - initial_retrievals,
            'model_calls': provider.calls - initial_calls, 'provider_input_chars': provider.input_chars - initial_chars,
            'generation_ms': sum(durations), 'paid_cost_usd': 0,
        }
    assert report['baseline']['fixture_quality_accuracy'] == 2/3
    assert report['memory']['fixture_quality_accuracy'] == 1
    assert report['baseline']['keyword_retrievals'] == report['memory']['keyword_retrievals'] == 3
    assert report['baseline']['model_calls'] == 1 and report['memory']['model_calls'] == 2
    print(json.dumps({'benchmark': corpus['version'], 'provider': 'fixture-fake', 'results': report}, sort_keys=True))
