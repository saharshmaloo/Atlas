from types import SimpleNamespace
import pytest
from atlas.planning import validated_plan
from atlas.runs import RunBudgets
from tests.test_worker import setup_run


@pytest.mark.parametrize('steps', [
    [{'key': 'shell', 'kind': 'shell', 'question': 'execute'}],
    [{'key': 'a', 'kind': 'search', 'question': 'q', 'after': ['a']}],
    [{'key': 'a', 'kind': 'verify', 'question': 'q'}],
    [{'key': 'a', 'kind': 'search', 'question': 'q'}] * 2,
])
def test_rejects_unsafe_cyclic_or_duplicate_plans(steps):
    with pytest.raises(ValueError):
        validated_plan(SimpleNamespace(plan=lambda q: {'steps': steps}), 'objective', RunBudgets())


@pytest.mark.database
def test_planned_dependencies_execute_in_order_with_idempotent_verification(client):
    _, base, saved = setup_run(client)
    url = f"{base}/{saved['id']}"
    response = client.post(f'{url}/plan')
    assert response.status_code == 200
    assert [item['kind'] for item in response.json()['tasks']] == ['search', 'answer', 'verify']
    assert response.json()['plan_version'] == 'saved-evidence-v1'
    for position in range(3):
        result = client.post(f'{url}/step').json()['run']
        assert result['tasks'][position]['status'] == 'completed'
    assert result['status'] == 'completed'
    assert result['tasks'][2]['output']['verification_id']
    assert client.post(f'{url}/plan').status_code == 409
