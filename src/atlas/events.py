from datetime import datetime
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, ForeignKey, String, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from atlas.database import Base
from atlas.runs import ResearchRun, find_run
from atlas.workspaces import DatabaseSession


class RunEvent(Base):
    __tablename__ = 'research_events'
    run_id: Mapped[UUID] = mapped_column(ForeignKey('research_runs.id'), primary_key=True)
    sequence: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey('research_tasks.id'))
    kind: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    data: Mapped[dict] = mapped_column(JSONB)


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sequence: int
    task_id: UUID | None
    kind: str
    created_at: datetime
    data: dict


def emit_event(session, run, event_kind, task_id=None, **data):
    """Only bounded operational metadata; never log prompts, provider payloads, or secrets."""
    allowed = {'kind', 'attempt', 'duration_ms', 'status', 'tool_calls', 'model_calls_reserved', 'tokens_reserved', 'count', 'code'}
    if set(data) - allowed or len(event_kind) > 32 or any(not isinstance(v, (str, int, bool)) for v in data.values()):
        raise ValueError('Invalid event metadata')
    sequence = session.scalar(update(ResearchRun).where(ResearchRun.id == run.id)
                              .values(event_seq=ResearchRun.event_seq + 1).returning(ResearchRun.event_seq))
    session.add(RunEvent(run_id=run.id, sequence=sequence, task_id=task_id, kind=event_kind, data=data))


router = APIRouter(prefix='/workspaces/{workspace_id}/runs', tags=['research events'])


@router.get('/{run_id}/events', response_model=list[EventResponse])
def list_events(workspace_id: UUID, run_id: UUID, session: DatabaseSession,
    after: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 50):
    find_run(workspace_id, run_id, session)
    return list(session.scalars(select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.sequence > after)
                                .order_by(RunEvent.sequence).limit(limit)))
