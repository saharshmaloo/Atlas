from typing import Annotated, Callable
from uuid import UUID
from fastapi import APIRouter, Depends
from atlas.answers import AnswerProvider, get_answer_provider
from atlas.hybrid import get_embedding_factory
from atlas.reranking import CandidateReranker, get_reranker
from atlas.runs import find_run, get_run
from atlas.worker import claim_task, execute_claim
from atlas.workspaces import DatabaseSession

router = APIRouter(prefix='/workspaces/{workspace_id}/runs', tags=['research worker'])


@router.post('/{run_id}/step')
def step_run(workspace_id: UUID, run_id: UUID, session: DatabaseSession,
    provider: Annotated[AnswerProvider, Depends(get_answer_provider)],
    factory: Annotated[Callable, Depends(get_embedding_factory)],
    reranker: Annotated[CandidateReranker | None, Depends(get_reranker)]):
    find_run(workspace_id, run_id, session); session.rollback()
    claim = claim_task(session, workspace_id, run_id)
    if claim: execute_claim(session, claim, provider, factory, reranker)
    return {'claimed': claim is not None, 'run': get_run(workspace_id, run_id, session)}
