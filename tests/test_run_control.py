from uuid import UUID, uuid4
import pytest
from sqlalchemy.orm import Session
from atlas.worker import claim_task, finish_task
from tests.test_worker import setup_run
pytestmark = pytest.mark.database


def test_cancel_fences_inflight_work_and_resume_preserves_budget(client):
    ws, base, saved = setup_run(client)
    url = f"{base}/{saved['id']}"
    with Session(client.app.state.engine) as session:
        claim = claim_task(session, UUID(ws), UUID(saved['id']))
        result = client.post(f'{url}/cancel').json()
        assert result['status'] == 'cancelled' and result['tasks'][0]['status'] == 'cancelled'
        assert not finish_task(session, claim, output={'stale': True})
    assert not client.post(f'{url}/step').json()['claimed']
    resumed = client.post(f'{url}/resume').json()
    assert resumed['status'] == 'queued' and resumed['tool_calls'] == 1
    done = client.post(f'{url}/step').json()['run']
    assert done['status'] == 'completed' and done['tasks'][0]['attempt'] == 2
    assert done['tool_calls'] == 2
    assert client.post(f'{url}/resume').status_code == 409
    assert client.post(f'{url}/cancel').status_code == 409
    assert client.post(url.replace(ws, str(uuid4())) + '/cancel').status_code == 404


def test_cancel_before_start_and_idempotent_cancel(client):
    _, base, saved = setup_run(client)
    url = f"{base}/{saved['id']}"
    first = client.post(f'{url}/cancel').json()
    assert client.post(f'{url}/cancel').json() == first
    assert client.post(f'{url}/resume').status_code == 200
