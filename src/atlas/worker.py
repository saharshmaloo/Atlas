"""Durable saved-evidence research worker. Start explicitly; no startup background jobs."""
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4
import argparse
import time

from fastapi import HTTPException
from sqlalchemy import and_, create_engine, func, or_, select
from sqlalchemy.orm import Session
from atlas.answers import AnswerRequest, answer_question, get_answer_provider
from atlas.database import database_url
from atlas.embeddings import get_embedding_provider
from atlas.reranking import get_reranker
from atlas.runs import ResearchRun, ResearchTask, RunBudgets, transition_task
from atlas.search import retrieve_passages


@dataclass
class TaskClaim:
    task_id: UUID
    run_id: UUID
    workspace_id: UUID
    token: UUID
    kind: str
    question: str


def claim_task(session, workspace_id, run_id):
    run = session.scalar(select(ResearchRun).where(ResearchRun.id == run_id,
        ResearchRun.workspace_id == workspace_id).with_for_update(skip_locked=True))
    if run is None or run.status not in ('queued', 'running'):
        session.rollback(); return None
    now = session.scalar(select(func.now()))
    budgets = RunBudgets.model_validate(run.budgets)
    if run.started_at is None:
        run.started_at, run.deadline_at = now, now + timedelta(seconds=budgets.max_seconds)
    if now >= run.deadline_at:
        run.status = 'budget_exhausted'; session.commit(); return None
    active = session.scalar(select(func.count()).select_from(ResearchTask).where(
        ResearchTask.run_id == run.id, ResearchTask.status == 'running', ResearchTask.lease_until > now))
    if active >= budgets.max_concurrency:
        session.rollback(); return None
    candidates = list(session.scalars(select(ResearchTask).where(ResearchTask.run_id == run.id,
        or_(ResearchTask.status == 'queued', and_(ResearchTask.status == 'running', ResearchTask.lease_until <= now)))
        .order_by(ResearchTask.position, ResearchTask.id).with_for_update(skip_locked=True).limit(8)))
    states = dict(session.execute(select(ResearchTask.id, ResearchTask.status).where(ResearchTask.run_id == run.id)).all())
    task = next((item for item in candidates if all(states.get(UUID(dep)) == 'completed' for dep in item.depends_on)), None)
    if task is None:
        session.rollback(); return None
    if task.attempt >= budgets.max_attempts:
        task.status, task.error, run.status = 'failed', 'Attempt budget exhausted', 'failed'
        task.lease_token = task.lease_until = None
        session.commit(); return None
    calls = int(task.kind in ('answer', 'verify'))
    tokens = 52000 if task.kind == 'answer' else 196000 if task.kind == 'verify' else 0
    if (run.tool_calls + 1 > budgets.max_tool_calls or run.model_calls_reserved + calls > budgets.max_model_calls
        or run.tokens_reserved + tokens > budgets.max_model_tokens
        or (calls and (run.deadline_at - now).total_seconds() < 31)):
        run.status = 'budget_exhausted'; session.commit(); return None
    run.tool_calls += 1; run.model_calls_reserved += calls; run.tokens_reserved += tokens
    if task.status == 'running': transition_task(task, 'queued')
    transition_task(task, 'running')
    task.attempt += 1; task.lease_token = uuid4(); task.lease_until = now + timedelta(seconds=120)
    run.status = 'running'
    claim = TaskClaim(task.id, run.id, workspace_id, task.lease_token, task.kind, task.question)
    session.commit()
    return claim


def finish_task(session, claim, output=None, error=None):
    run = session.scalar(select(ResearchRun).where(ResearchRun.id == claim.run_id).with_for_update())
    task = session.scalar(select(ResearchTask).where(ResearchTask.id == claim.task_id).with_for_update())
    if task is None or task.lease_token != claim.token or task.status != 'running':
        session.rollback(); return False
    retry = error and task.attempt < RunBudgets.model_validate(run.budgets).max_attempts
    transition_task(task, 'queued' if retry else 'failed' if error else 'completed')
    task.output, task.error = output, error
    task.lease_token = task.lease_until = None
    session.flush()
    states = list(session.scalars(select(ResearchTask.status).where(ResearchTask.run_id == run.id)))
    run.status = 'failed' if 'failed' in states else 'completed' if all(s == 'completed' for s in states) else 'running'
    if run.deadline_at and session.scalar(select(func.now())) >= run.deadline_at:
        run.status = 'budget_exhausted'
    session.commit()
    return True


def execute_claim(session, claim, provider, embedding_factory=get_embedding_provider, reranker=None, verifier=None):
    current = session.get(ResearchTask, claim.task_id)
    if current is None or current.lease_token != claim.token or current.status != 'running': return False
    session.rollback()
    try:
        if claim.kind == 'answer':
            result = answer_question(claim.workspace_id, AnswerRequest(question=claim.question), session,
                provider, embedding_factory, reranker, idempotency_key=f'research-task:{claim.task_id}')
            output = {'answer_id': str(result.id), 'status': result.status}
        elif claim.kind == 'verify':
            from atlas.verification import get_claim_verifier
            from atlas.verification_api import check_support
            dependencies = list(session.scalars(select(ResearchTask).where(ResearchTask.run_id == claim.run_id,
                ResearchTask.id.in_([UUID(dep) for dep in current.depends_on]))))
            answer_id = next(UUID(item.output['answer_id']) for item in dependencies if item.output and 'answer_id' in item.output)
            result = check_support(claim.workspace_id, answer_id, session, verifier or get_claim_verifier(),
                                   idempotency_key=f'research-task:{claim.task_id}')
            output = {'verification_id': str(result.id), 'answer_id': str(answer_id)}
        elif claim.kind == 'search':
            output = {'passage_ids': [str(item.id) for item in retrieve_passages(claim.workspace_id, session, claim.question, 5)]}
            session.rollback()
        else:
            raise ValueError('Unknown task tool')
        return finish_task(session, claim, output=output)
    except Exception as error:
        session.rollback()
        category = f'HTTP {error.status_code}' if isinstance(error, HTTPException) else 'execution error'
        return finish_task(session, claim, error=f'Task failed ({category})')


def run_once(engine, provider=None):
    with Session(engine) as session:
        candidates = session.execute(select(ResearchRun.workspace_id, ResearchRun.id).where(
            ResearchRun.status.in_(['queued', 'running'])).order_by(ResearchRun.created_at, ResearchRun.id).limit(100)).all()
        session.rollback()
        for workspace_id, run_id in candidates:
            claim = claim_task(session, workspace_id, run_id)
            if claim:
                execute_claim(session, claim, provider or get_answer_provider(), reranker=get_reranker())
                return True
    return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch', action='store_true', help='Poll every two seconds; otherwise process at most one task')
    args = parser.parse_args()
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        while True:
            worked = run_once(engine)
            if not args.watch: break
            if not worked: time.sleep(2)
    finally:
        engine.dispose()
