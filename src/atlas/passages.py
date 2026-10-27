import re
from bisect import bisect_right
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID, uuid5

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, mapped_column

from atlas.database import Base
from atlas.sources import Source, find_source
from atlas.workspaces import DatabaseSession

CHUNKER_VERSION = "paragraph-v1"
MAX_PASSAGE_CHARS = 1000


def passage_spans(content: str) -> Iterator[tuple[int, int]]:
    """Partition text without normalization, gaps, or overlap (Python string offsets)."""
    boundaries = [match.end() for match in re.finditer(r"\r?\n[ \t]*\r?\n", content)]
    start = 0
    while start < len(content):
        end = min(start + MAX_PASSAGE_CHARS, len(content))
        if end < len(content):
            index = bisect_right(boundaries, end)
            if index and boundaries[index - 1] > start:
                end = boundaries[index - 1]
        yield start, end
        start = end


class Passage(Base):
    __tablename__ = "passages"
    __table_args__ = (
        UniqueConstraint("source_id", "position", name="passage_source_position"),
        CheckConstraint("position >= 0", name="passage_position_nonnegative"),
        CheckConstraint("start_char >= 0 AND end_char > start_char", name="passage_valid_span"),
        CheckConstraint("char_length(text) = end_char - start_char", name="passage_text_length"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("sources.id"))
    position: Mapped[int]
    start_char: Mapped[int]
    end_char: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    chunker_version: Mapped[str] = mapped_column(String(32))


class PassageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    position: int
    start_char: int
    end_char: int
    text: str
    chunker_version: str


class GenerationResponse(BaseModel):
    source_id: UUID
    passage_count: int


router = APIRouter(
    prefix="/workspaces/{workspace_id}/sources/{source_id}/passages", tags=["passages"]
)


@router.post("", response_model=GenerationResponse)
def generate_passages(workspace_id: UUID, source_id: UUID, session: DatabaseSession):
    # Serialize concurrent generators for this source until the transaction commits.
    source = session.scalar(
        select(Source)
        .where(Source.id == source_id, Source.workspace_id == workspace_id)
        .with_for_update()
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    count = session.scalar(select(func.count(Passage.id)).where(Passage.source_id == source_id))
    if count == 0:
        content = source.content
        for position, (start, end) in enumerate(passage_spans(content)):
            session.add(Passage(
                id=uuid5(source_id, f"{CHUNKER_VERSION}:{start}:{end}"),
                source_id=source_id, position=position, start_char=start, end_char=end,
                text=content[start:end], chunker_version=CHUNKER_VERSION,
            ))
            count += 1
    session.commit()
    return GenerationResponse(source_id=source_id, passage_count=count)


@router.get("", response_model=list[PassageResponse])
def list_passages(
    workspace_id: UUID,
    source_id: UUID,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Passage]:
    find_source(workspace_id, source_id, session)
    query = (
        select(Passage).where(Passage.source_id == source_id)
        .order_by(Passage.position).limit(limit).offset(offset)
    )
    return list(session.scalars(query))
