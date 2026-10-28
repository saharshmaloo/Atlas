from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from atlas.passages import Passage, PassageResponse
from atlas.sources import Source, require_workspace
from atlas.workspaces import DatabaseSession


class SearchResult(PassageResponse):
    source_title: str
    score: float


router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["search"])


@router.get("/search", response_model=list[SearchResult])
def search_passages(
    workspace_id: UUID,
    session: DatabaseSession,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[SearchResult]:
    q = q.strip()
    if not q or "\x00" in q:
        raise HTTPException(status_code=422, detail="Query must contain text and no NUL characters")
    return retrieve_passages(workspace_id, session, q, limit)


def retrieve_passages(workspace_id, session, query_text: str, limit: int) -> list[SearchResult]:
    require_workspace(workspace_id, session)
    terms = func.websearch_to_tsquery("english", query_text)
    score = func.ts_rank_cd(Passage.search_vector, terms).label("score")
    query = (
        select(
            Passage.id, Passage.source_id, Passage.position, Passage.start_char,
            Passage.end_char, Passage.text, Passage.chunker_version,
            Source.title.label("source_title"), score,
        )
        .join(Source, Passage.source_id == Source.id)
        .where(Source.workspace_id == workspace_id, Passage.search_vector.bool_op("@@")(terms))
        .order_by(score.desc(), Passage.source_id, Passage.position, Passage.id)
        .limit(limit)
    )
    return [SearchResult.model_validate(row) for row in session.execute(query).mappings()]
