from uuid import UUID
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from atlas.worker import claim_task, execute_claim
pytestmark = pytest.mark.database


def create(client, budgets):
    ws = client.post('/workspaces', json={'name': 'Budget'}).json()['id']
    base = f'/workspaces/{ws}/runs'
    saved = client.post(base, json={'objective': 'Evidence', 'budgets': budgets}).json()
    return ws, base, saved


@pytest.mark.parametrize('budgets', [{'max_tool_calls': 0}, {'max_model_calls': 0}, {'max_model_tokens': 1}, {'max_seconds': 1}])
def test_reservations_stop_work_before_external_effects(client, budgets):
    ws, base, saved = create(client, budgets)
    result = client.post(f"{base}/{saved['id']}/step").json()
    assert not result['claimed'] and result['run']['status'] == 'budget_exhausted'
    assert client.get(f'/workspaces/{ws}/answers').json() == []
    assert result['run']['tool_calls'] == 0


def test_deadline_and_concurrency_survive_restarts(client):
    ws, base, saved = create(client, {'max_concurrency': 1})
    with Session(client.app.state.engine) as session:
        claim = claim_task(session, UUID(ws), UUID(saved['id']))
        assert claim and claim_task(session, UUID(ws), UUID(saved['id'])) is None
        session.execute(text("UPDATE research_runs SET deadline_at = now() - interval '1 second'")); session.commit()
        assert claim_task(session, UUID(ws), UUID(saved['id'])) is None
    assert client.get(f"{base}/{saved['id']}").json()['status'] == 'budget_exhausted'


def test_attempt_budget_bounds_retries_and_sanitizes_errors(client):
    ws, base, saved = create(client, {'max_attempts': 2})
    with Session(client.app.state.engine) as session:
        for attempt in range(2):
            claim = claim_task(session, UUID(ws), UUID(saved['id']))
            claim.kind = 'unknown-tool-secret'
            assert execute_claim(session, claim, None)
        assert claim_task(session, UUID(ws), UUID(saved['id'])) is None
    result = client.get(f"{base}/{saved['id']}").json()
    assert result['status'] == 'failed' and result['tasks'][0]['attempt'] == 2
    assert 'secret' not in result['tasks'][0]['error']
    assert result['model_calls_reserved'] == 2 and result['tokens_reserved'] == 104000


def test_inflight_checkpoint_cannot_reactivate_exhausted_run(client):
    from atlas.worker import finish_task
    ws, base, saved = create(client, {'max_tool_calls': 1})
    with Session(client.app.state.engine) as session:
        claim = claim_task(session, UUID(ws), UUID(saved['id']))
        session.execute(text("UPDATE research_runs SET status = 'budget_exhausted'")); session.commit()
        assert finish_task(session, claim, output={'completed_reserved_work': True})
    assert client.get(f"{base}/{saved['id']}").json()['status'] == 'budget_exhausted'
