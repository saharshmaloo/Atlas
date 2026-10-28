from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from atlas.embeddings import EmbeddingError, EmbeddingProvider, PassageEmbedding, embed_batch, get_embedding_provider
from atlas.passages import Passage
from atlas.search import SearchResult
from atlas.sources import Source, require_workspace
from atlas.workspaces import DatabaseSession

MAX_EXACT_VECTORS = 1000


def vector_results(workspace_id, session, q, limit, provider):
    require_workspace(workspace_id, session)
    rows = session.execute(select(PassageEmbedding.vector, Passage, Source).join(Passage,
        Passage.id == PassageEmbedding.passage_id).join(Source, Source.id == Passage.source_id).where(
        Source.workspace_id == workspace_id, PassageEmbedding.profile_id == provider.spec.id)
        .order_by(Passage.id).limit(MAX_EXACT_VECTORS + 1)).all()
    if len(rows) > MAX_EXACT_VECTORS:
        raise HTTPException(422, 'Workspace exceeds the exact vector retrieval limit of 1000 passages')
    if not rows: return []
    try:
        query = embed_batch(provider, [q])[0]
    except (EmbeddingError, TimeoutError):
        raise HTTPException(502, 'Query embedding failed') from None
    results = []
    for vector, passage, source in rows:
        score = sum(a * b for a, b in zip(query, vector))
        results.append(SearchResult(**{key: getattr(passage, key) for key in SearchResult.model_fields
            if key in ('id', 'source_id', 'position', 'start_char', 'end_char', 'text', 'chunker_version')},
            score=score, source_title=source.title, source_kind=source.kind, source_version=source.version,
            source_document_id=source.document_id, locations=[loc for loc in source.locations
                if loc['start_char'] < passage.end_char and loc['end_char'] > passage.start_char]))
    return sorted(results, key=lambda row: (-row.score, row.source_id, row.position, row.id))[:limit]


router = APIRouter(prefix='/workspaces/{workspace_id}', tags=['vector retrieval'])


@router.get('/vector-search', response_model=list[SearchResult])
def vector_search(workspace_id: UUID, session: DatabaseSession,
    provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    q: Annotated[str, Query(min_length=1, max_length=500)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10):
    if not q.strip() or '\0' in q: raise HTTPException(422, 'Enter a query without NUL characters')
    return vector_results(workspace_id, session, q.strip(), limit, provider)
