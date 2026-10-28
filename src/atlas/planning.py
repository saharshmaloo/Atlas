from typing import Annotated, Literal, Protocol
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete
from atlas.run_control import locked_run
from atlas.runs import ResearchTask, RunBudgets, get_run
from atlas.workspaces import DatabaseSession


class PlanStep(BaseModel):
    key: str = Field(min_length=1, max_length=40, pattern=r'^[a-zA-Z0-9_-]+$')
    kind: Literal['search', 'answer', 'verify']
    question: str = Field(min_length=1, max_length=500)
    after: list[str] = Field(default_factory=list, max_length=8)


class Plan(BaseModel):
    steps: list[PlanStep] = Field(min_length=1, max_length=8)


class ResearchPlanner(Protocol):
    identity: str
    def plan(self, objective) -> Plan: ...


class SavedEvidencePlanner:
    identity = 'saved-evidence-v1'
    def plan(self, objective):
        return Plan(steps=[PlanStep(key='search', kind='search', question=objective),
            PlanStep(key='answer', kind='answer', question=objective, after=['search']),
            PlanStep(key='verify', kind='verify', question=objective, after=['answer'])])


def get_planner() -> ResearchPlanner:
    return SavedEvidencePlanner()


def validated_plan(planner, objective, budgets):
    plan = Plan.model_validate(planner.plan(objective))
    seen = {}
    for step in plan.steps:
        if step.key in seen or not set(step.after) <= set(seen) or not step.question.strip() or '\0' in step.question:
            raise ValueError('Plan must be an ordered acyclic graph with unique keys and valid questions')
        if step.kind == 'verify' and not any(seen[key] == 'answer' for key in step.after):
            raise ValueError('Verification requires a prior answer dependency')
        seen[step.key] = step.kind
    calls = sum(step.kind != 'search' for step in plan.steps)
    tokens = sum(52000 if step.kind == 'answer' else 196000 if step.kind == 'verify' else 0 for step in plan.steps)
    if len(plan.steps) > budgets.max_tool_calls or calls > budgets.max_model_calls or tokens > budgets.max_model_tokens:
        raise ValueError('Plan exceeds execution budgets')
    return plan


router = APIRouter(prefix='/workspaces/{workspace_id}/runs', tags=['research planning'])


@router.post('/{run_id}/plan')
def plan_run(workspace_id: UUID, run_id: UUID, session: DatabaseSession,
             planner: Annotated[ResearchPlanner, Depends(get_planner)]):
    run, tasks = locked_run(workspace_id, run_id, session)
    if run.status != 'queued' or any(task.attempt for task in tasks):
        raise HTTPException(409, 'Only an unstarted run can be planned')
    try:
        plan = validated_plan(planner, run.objective, RunBudgets.model_validate(run.budgets))
        if not planner.identity or len(planner.identity) > 100 or '\0' in planner.identity: raise ValueError()
    except (ValueError, TimeoutError):
        raise HTTPException(422, 'Planner returned an invalid, unsafe, or over-budget plan') from None
    session.execute(delete(ResearchTask).where(ResearchTask.run_id == run.id))
    ids = {step.key: uuid4() for step in plan.steps}
    for position, step in enumerate(plan.steps):
        session.add(ResearchTask(id=ids[step.key], run_id=run.id, position=position, kind=step.kind,
            question=step.question.strip(), depends_on=[str(ids[key]) for key in step.after]))
    run.plan_version = planner.identity
    session.commit()
    return get_run(workspace_id, run_id, session)
