from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from atlas.main import create_app
from atlas.runs import transition_task


def test_task_state_transitions_are_explicit():
    task = SimpleNamespace(status='queued')
    with pytest.raises(ValueError): transition_task(task, 'completed')
    for state in ['running', 'queued', 'running', 'failed', 'queued', 'cancelled', 'queued', 'running', 'completed']:
        transition_task(task, state)
    with pytest.raises(ValueError): transition_task(task, 'running')


@pytest.mark.database
def test_runs_persist_and_remain_workspace_scoped(client, database):
    ws = client.post('/workspaces', json={'name': 'Runs'}).json()['id']
    base = f'/workspaces/{ws}/runs'
    response = client.post(base, json={'objective': '  transactions  '})
    assert response.status_code == 201
    saved = response.json()
    assert saved['status'] == 'queued' and saved['tasks'][0]['kind'] == 'answer'
    assert saved['objective'] == 'transactions'
    with TestClient(create_app(database[0])) as restarted:
        assert restarted.get(f"{base}/{saved['id']}").json() == saved
    assert len(client.get(base).json()) == 1
    assert client.get(f"/workspaces/{uuid4()}/runs/{saved['id']}").status_code == 404
    for value in ['', ' ', 'bad\0text', 'x' * 501]:
        assert client.post(base, json={'objective': value}).status_code == 422
