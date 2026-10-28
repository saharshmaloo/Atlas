from dataclasses import replace
from uuid import UUID, uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from atlas.worker import claim_task, execute_claim, finish_task, run_once
pytestmark = pytest.mark.database


def setup_run(client):
    ws = client.post('/workspaces', json={'name': 'Worker'}).json()['id']
    base = f'/workspaces/{ws}/runs'
    saved = client.post(base, json={'objective': 'unmatched'}).json()
    return ws, base, saved


def test_worker_executes_persisted_task_once(client):
    ws, base, saved = setup_run(client)
    assert run_once(client.app.state.engine)
    result = client.get(f"{base}/{saved['id']}").json()
    assert result['status'] == 'completed' and result['tasks'][0]['attempt'] == 1
    assert result['tasks'][0]['output']['answer_id']
    assert not run_once(client.app.state.engine)
    assert len(client.get(f'/workspaces/{ws}/answers').json()) == 1


def test_expired_lease_recovery_fences_stale_workers(client):
    ws, base, saved = setup_run(client)
    with Session(client.app.state.engine) as session:
        first = claim_task(session, UUID(ws), UUID(saved['id']))
        assert first
        assert claim_task(session, UUID(ws), UUID(saved['id'])) is None
        session.execute(text("UPDATE research_tasks SET lease_until = now() - interval '1 second'")); session.commit()
        second = claim_task(session, UUID(ws), UUID(saved['id']))
        assert second and second.token != first.token
        assert not finish_task(session, first, output={'stale': True})
        assert not finish_task(session, replace(second, token=uuid4()), output={'stale': True})
        assert execute_claim(session, second, None)
    result = client.get(f"{base}/{saved['id']}").json()
    assert result['tasks'][0]['attempt'] == 2 and result['status'] == 'completed'


def test_answer_effect_is_idempotent_after_worker_checkpoint_loss(client, monkeypatch):
    from atlas import worker
    ws, base, saved = setup_run(client)
    original = worker.finish_task
    monkeypatch.setattr(worker, 'finish_task', lambda *args, **kwargs: False)
    assert run_once(client.app.state.engine)
    answers = client.get(f'/workspaces/{ws}/answers').json()
    assert len(answers) == 1
    with client.app.state.engine.begin() as connection:
        connection.execute(text("UPDATE research_tasks SET lease_until = now() - interval '1 second'"))
    monkeypatch.setattr(worker, 'finish_task', original)
    assert run_once(client.app.state.engine)
    assert client.get(f'/workspaces/{ws}/answers').json() == answers
    assert client.get(f"{base}/{saved['id']}").json()['status'] == 'completed'


def test_concurrent_workers_claim_only_one_lease(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    ws, base, saved = setup_run(client)
    barrier = Barrier(2)
    def claim():
        with Session(client.app.state.engine) as session:
            barrier.wait(timeout=5)
            return claim_task(session, UUID(ws), UUID(saved['id']))
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: claim(), range(2)))
    assert sum(item is not None for item in results) == 1
    run = client.get(f"{base}/{saved['id']}").json()
    assert run['tasks'][0]['attempt'] == 1 and run['tool_calls'] == 1
