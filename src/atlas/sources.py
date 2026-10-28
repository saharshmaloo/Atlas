from datetime import datetime
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Text, UniqueConstraint, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from starlette.responses import JSONResponse

from atlas.database import Base
from atlas.workspaces import DatabaseSession, Workspace

MAX_SOURCE_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = MAX_SOURCE_BYTES + 64 * 1024


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint('workspace_id', 'document_id', 'version', name='source_document_version'),)
    document_id: Mapped[UUID] = mapped_column(default=uuid4)
    version: Mapped[int] = mapped_column(server_default='1')
    kind: Mapped[str] = mapped_column(String(16), server_default='text')
    locations: Mapped[list] = mapped_column(JSONB, server_default='[]')
    extractor: Mapped[str | None] = mapped_column(String(32))
    original_data: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    original_uri: Mapped[str | None] = mapped_column(String(2048))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, deferred=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    title: str
    content_hash: str
    document_id: UUID
    version: int
    kind: str
    locations: list[dict]
    extractor: str | None
    original_uri: str | None
    retrieved_at: datetime | None
    created_at: datetime


class UploadLimitMiddleware:
    """Bound multipart bodies before parsing, including chunked requests."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and scope["path"].rstrip("/").endswith(("/sources", "/versions", "/pdf"))
        ):
            messages, size = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                size += len(message.get("body", b""))
                if size > MAX_REQUEST_BYTES:
                    response = JSONResponse({"detail": "Upload request too large"}, status_code=413)
                    await response(scope, receive, send)
                    return
                messages.append(message)
                if not message.get("more_body", False):
                    break
            original_receive, pending = receive, iter(messages)

            async def receive():
                return next(pending, None) or await original_receive()

        await self.app(scope, receive, send)


router = APIRouter(prefix="/workspaces/{workspace_id}/sources", tags=["sources"])


def require_workspace(workspace_id: UUID, session: DatabaseSession) -> None:
    if session.get(Workspace, workspace_id) is None:
        raise HTTPException(status_code=404, detail="Workspace not found")


def find_source(workspace_id: UUID, source_id: UUID, session: DatabaseSession) -> Source:
    source = session.scalar(
        select(Source).where(Source.id == source_id, Source.workspace_id == workspace_id)
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.post("", response_model=SourceResponse, status_code=201)
def upload_source(workspace_id: UUID, file: UploadFile, session: DatabaseSession) -> Source:
    require_workspace(workspace_id, session)
    source = text_source(workspace_id, file)
    session.add(source); session.commit(); session.refresh(source)
    return source


def text_source(workspace_id, file):
    title = PurePosixPath((file.filename or "").replace("\\", "/")).name.strip()
    if not title.lower().endswith(".txt") or len(title) > 200 or "\x00" in title:
        raise HTTPException(
            status_code=422, detail="Filename must end in .txt and contain at most 200 characters"
        )
    data = file.file.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="Source exceeds 1 MiB")
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="Source must be valid UTF-8")
    if not content.lstrip("\ufeff").strip() or "\x00" in content:
        raise HTTPException(status_code=422, detail="Source must contain text and no NUL characters")
    source = Source(
        workspace_id=workspace_id, title=title, content=content, content_hash=sha256(data).hexdigest()
    )
    return source


@router.get("", response_model=list[SourceResponse])
def list_sources(
    workspace_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Source]:
    require_workspace(workspace_id, session)
    query = (
        select(Source)
        .where(Source.workspace_id == workspace_id)
        .order_by(Source.created_at, Source.id)
        .limit(limit)
        .offset(offset)
    )
    return list(session.scalars(query))


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(workspace_id: UUID, source_id: UUID, session: DatabaseSession) -> Source:
    return find_source(workspace_id, source_id, session)


@router.get("/{source_id}/content", response_class=PlainTextResponse)
def get_content(workspace_id: UUID, source_id: UUID, session: DatabaseSession) -> PlainTextResponse:
    return PlainTextResponse(find_source(workspace_id, source_id, session).content)


@router.post('/{source_id}/versions', response_model=SourceResponse, status_code=201)
def add_version(workspace_id: UUID, source_id: UUID, file: UploadFile, session: DatabaseSession):
    previous = find_source(workspace_id, source_id, session)
    if previous.kind != 'text': raise HTTPException(409, 'Use the matching PDF or webpage ingestion endpoint for a new version')
    source = text_source(workspace_id, file)
    assign_version(source, previous, session)
    session.add(source); session.commit(); session.refresh(source)
    return source


@router.get('/{source_id}/versions', response_model=list[SourceResponse])
def list_versions(workspace_id: UUID, source_id: UUID, session: DatabaseSession,
                  offset: Annotated[int, Query(ge=0)] = 0):
    source = find_source(workspace_id, source_id, session)
    return list(session.scalars(select(Source).where(Source.workspace_id == workspace_id,
        Source.document_id == source.document_id).order_by(Source.version).offset(offset).limit(50)))


@router.get('/{source_id}/duplicates', response_model=list[SourceResponse])
def find_duplicates(workspace_id: UUID, source_id: UUID, session: DatabaseSession,
                    offset: Annotated[int, Query(ge=0)] = 0):
    """Duplicates remain distinct immutable uploads/versions, scoped to a workspace."""
    source = find_source(workspace_id, source_id, session)
    return list(session.scalars(select(Source).where(Source.workspace_id == workspace_id,
        Source.content_hash == source.content_hash, Source.id != source.id)
        .order_by(Source.created_at, Source.id).offset(offset).limit(50)))


def assign_version(source, previous, session):
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'),
                    {'key': str(previous.document_id)})
    version = session.scalar(select(func.max(Source.version)).where(
        Source.workspace_id == previous.workspace_id, Source.document_id == previous.document_id)) + 1
    source.document_id, source.version = previous.document_id, version
