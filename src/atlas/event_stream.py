from time import monotonic, sleep
from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from atlas.events import EventResponse, RunEvent
from atlas.runs import find_run
from atlas.workspaces import DatabaseSession

router = APIRouter(prefix='/workspaces/{workspace_id}/runs', tags=['event stream'])


@router.get('/{run_id}/events/stream')
def stream_events(workspace_id: UUID, run_id: UUID, request: Request, session: DatabaseSession,
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header()] = None):
    find_run(workspace_id, run_id, session)
    session.rollback()
    if last_event_id is not None:
        try:
            cursor = int(last_event_id)
            if cursor < 0: raise ValueError()
            after = max(after, cursor)
        except ValueError: raise HTTPException(422, 'Invalid Last-Event-ID') from None
    engine = request.app.state.engine
    def generate():
        cursor, deadline = after, monotonic() + 10
        while monotonic() < deadline:
            with Session(engine) as read:
                run = find_run(workspace_id, run_id, read)
                events = list(read.scalars(select(RunEvent).where(RunEvent.run_id == run_id,
                    RunEvent.sequence > cursor).order_by(RunEvent.sequence).limit(100)))
                serialized = [(event.sequence, EventResponse.model_validate(event).model_dump_json()) for event in events]
                terminal = run.status not in ('queued', 'running')
                last = run.event_seq
            for sequence, data in serialized:
                cursor = sequence
                yield f'id: {sequence}\nevent: progress\ndata: {data}\n\n'
            if terminal and cursor >= last: return
            if not serialized:
                yield ': heartbeat\n\n'
                sleep(.25)
    return StreamingResponse(generate(), media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
