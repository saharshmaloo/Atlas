from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, ForeignKey, String, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from atlas.database import Base
from atlas.sources import require_workspace
from atlas.workspaces import DatabaseSession

State = Literal['queued', 'running', 'completed', 'failed', 'cancelled', 'budget_exhausted']


class RunBudgets(BaseModel):
    max_attempts: int = Field(default=3, ge=1, le=5)
    max_concurrency: int = Field(default=1, ge=1, le=4)
    max_model_calls: int = Field(default=3, ge=0, le=100)
    max_tool_calls: int = Field(default=8, ge=0, le=100)
    max_seconds: int = Field(default=300, ge=1, le=3600)
    max_model_tokens: int = Field(default=500000, ge=0, le=10000000)


class ResearchRun(Base):
    __tablename__ = 'research_runs'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey('workspaces.id'), index=True)
    event_seq: Mapped[int] = mapped_column(server_default='0')
    plan_version: Mapped[str | None] = mapped_column(String(100))
    budgets: Mapped[dict] = mapped_column(JSONB)
    model_calls_reserved: Mapped[int] = mapped_column(server_default='0')
    tool_calls: Mapped[int] = mapped_column(server_default='0')
    tokens_reserved: Mapped[int] = mapped_column(server_default='0')
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    objective: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), server_default='queued')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResearchTask(Base):
    __tablename__ = 'research_tasks'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey('research_runs.id'), index=True)
    position: Mapped[int]
    kind: Mapped[str] = mapped_column(String(16))
    question: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), server_default='queued')
    depends_on: Mapped[list] = mapped_column(JSONB, server_default='[]')
    attempt: Mapped[int] = mapped_column(server_default='0')
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(200))


class RunRequest(BaseModel):
    budgets: RunBudgets = Field(default_factory=RunBudgets)
    objective: str = Field(min_length=1, max_length=500)

    @field_validator('objective')
    @classmethod
    def validate_objective(cls, value):
        if not value.strip() or '\0' in value: raise ValueError('Enter a nonblank objective without NUL characters')
        return value.strip()


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    position: int
    kind: str
    question: str
    status: State
    depends_on: list[UUID]
    attempt: int
    lease_until: datetime | None
    output: dict | None
    error: str | None


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workspace_id: UUID
    objective: str
    event_seq: int
    plan_version: str | None
    budgets: RunBudgets
    model_calls_reserved: int
    tool_calls: int
    tokens_reserved: int
    started_at: datetime | None
    deadline_at: datetime | None
    status: State
    created_at: datetime


class RunDetail(RunSummary):
    tasks: list[TaskResponse]


def find_run(workspace_id, run_id, session):
    run = session.scalar(select(ResearchRun).where(ResearchRun.id == run_id, ResearchRun.workspace_id == workspace_id))
    if run is None: raise HTTPException(404, 'Research run not found')
    return run


def transition_task(task, state):
    allowed = {'queued': {'running', 'cancelled'}, 'running': {'completed', 'failed', 'queued', 'cancelled'},
               'failed': {'queued'}, 'completed': set(), 'cancelled': {'queued'}}
    if state not in allowed.get(task.status, set()): raise ValueError('Invalid task state transition')
    task.status = state


router = APIRouter(prefix='/workspaces/{workspace_id}/runs', tags=['research runs'])


@router.post('', response_model=RunDetail, status_code=201)
def create_run(workspace_id: UUID, body: RunRequest, session: DatabaseSession):
    require_workspace(workspace_id, session)
    run = ResearchRun(workspace_id=workspace_id, objective=body.objective, budgets=body.budgets.model_dump())
    session.add(run); session.flush()
    session.add(ResearchTask(run_id=run.id, position=0, kind='answer', question=body.objective))
    from atlas.events import emit_event
    emit_event(session, run, 'created', status='queued')
    session.commit()
    return get_run(workspace_id, run.id, session)


@router.get('', response_model=list[RunSummary])
def list_runs(workspace_id: UUID, session: DatabaseSession,
              limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0):
    require_workspace(workspace_id, session)
    return list(session.scalars(select(ResearchRun).where(ResearchRun.workspace_id == workspace_id)
        .order_by(ResearchRun.created_at.desc(), ResearchRun.id.desc()).offset(offset).limit(limit)))


@router.get('/{run_id}', response_model=RunDetail)
def get_run(workspace_id: UUID, run_id: UUID, session: DatabaseSession):
    run = find_run(workspace_id, run_id, session)
    tasks = list(session.scalars(select(ResearchTask).where(ResearchTask.run_id == run.id)
                                .order_by(ResearchTask.position, ResearchTask.id)))
    return RunDetail(**RunSummary.model_validate(run).model_dump(), tasks=tasks)
