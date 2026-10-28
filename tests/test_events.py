from uuid import uuid4
import pytest
from tests.test_worker import setup_run
pytestmark = pytest.mark.database


def test_events_are_ordered_resumable_scoped_and_exclude_input(client):
    ws, base, saved = setup_run(client)
    url = f"{base}/{saved['id']}"
    client.post(f'{url}/plan')
    for _ in range(3): client.post(f'{url}/step')
    response = client.get(f'{url}/events')
    assert response.status_code == 200
    events = response.json()
    assert [row['sequence'] for row in events] == list(range(1, 9))
    assert [row['kind'] for row in events] == ['created', 'planned'] + ['task_started', 'task_completed'] * 3
    assert client.get(f'{url}/events?after=3&limit=2').json() == events[3:5]
    assert 'unmatched' not in response.text
    assert events[-1]['data']['status'] == 'completed'
    assert events[-1]['data']['duration_ms'] >= 0
    assert client.get(url.replace(ws, str(uuid4())) + '/events').status_code == 404
