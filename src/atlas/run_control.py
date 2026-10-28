from uuid import UUID
from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select
from atlas.events import emit_event
from atlas.runs import ResearchRun, ResearchTask, RunBudgets, get_run
from atlas.workspaces import DatabaseSession

router = APIRouter(prefix='/workspaces/{workspace_id}/runs', tags=['run controls'])


def locked_run(workspace_id, run_id, session):
    run = session.scalar(select(ResearchRun).where(ResearchRun.id == run_id,
        ResearchRun.workspace_id == workspace_id).with_for_update())
    if run is None: raise HTTPException(404, 'Research run not found')
    tasks = list(session.scalars(select(ResearchTask).where(ResearchTask.run_id == run.id).with_for_update()))
    return run, tasks


@router.post('/{run_id}/cancel')
def cancel_run(workspace_id: UUID, run_id: UUID, session: DatabaseSession):
    run, tasks = locked_run(workspace_id, run_id, session)
    if run.status == 'completed': raise HTTPException(409, 'Completed runs cannot be cancelled')
    if run.status != 'cancelled': emit_event(session, run, 'cancelled', status='cancelled')
    run.status = 'cancelled'
    for task in tasks:
        if task.status != 'completed':
            task.status = 'cancelled'; task.lease_token = task.lease_until = None
    session.commit()
    return get_run(workspace_id, run_id, session)


@router.post('/{run_id}/resume')
def resume_run(workspace_id: UUID, run_id: UUID, session: DatabaseSession):
    run, tasks = locked_run(workspace_id, run_id, session)
    if run.status not in ('cancelled', 'failed'): raise HTTPException(409, 'Only cancelled or failed runs can resume')
    budgets = RunBudgets.model_validate(run.budgets)
    if ((run.deadline_at and session.scalar(select(func.now())) >= run.deadline_at)
        or run.tool_calls >= budgets.max_tool_calls
        or any(task.status != 'completed' and task.attempt >= budgets.max_attempts for task in tasks)):
        raise HTTPException(409, 'Execution budget is exhausted; create a new run with explicit budgets')
    for task in tasks:
        if task.status != 'completed':
            task.status = 'queued'; task.lease_token = task.lease_until = None
    run.status = 'queued'
    emit_event(session, run, 'resumed', status='queued')
    session.commit()
    return get_run(workspace_id, run_id, session)
