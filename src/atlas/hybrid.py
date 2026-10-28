from typing import Annotated, Callable
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from atlas.embeddings import get_embedding_provider
from atlas.reranking import CandidateReranker, get_reranker, rerank_candidates
from atlas.search import retrieve_passages
from atlas.vector_search import vector_results
from atlas.workspaces import DatabaseSession


def rank_fusion(lists, limit, constant=60):
    scores, items = {}, {}
    for ranked in lists:
        seen = set()
        for position, item in enumerate(ranked, 1):
            if item.id in seen: continue
            seen.add(item.id); items[item.id] = item
            scores[item.id] = scores.get(item.id, 0) + 1 / (constant + position)
    ordered = sorted(items.values(), key=lambda item: (-scores[item.id], item.source_id, item.position, item.id))
    return [item.model_copy(update={'score': scores[item.id]}) for item in ordered[:limit]]


def get_embedding_factory():
    return get_embedding_provider


def hybrid_results(workspace_id, session, q, limit, factory, vector_query=None):
    keyword = retrieve_passages(workspace_id, session, q, 50)
    try:
        vectors = vector_results(workspace_id, session, vector_query or q, 50, factory())
    except HTTPException as error:
        if error.status_code not in (422, 502, 503, 504): raise
        return keyword[:limit], 'keyword-fallback-v1'
    # Explicit threshold avoids adding orthogonal/negative evidence to keyword results.
    vectors = [item for item in vectors if item.score >= .2]
    return rank_fusion([keyword, vectors], limit), 'hybrid-rrf60-v1'


router = APIRouter(prefix='/workspaces/{workspace_id}', tags=['hybrid retrieval'])


@router.get('/hybrid-search')
def hybrid_search(workspace_id: UUID, session: DatabaseSession,
    factory: Annotated[Callable, Depends(get_embedding_factory)],
    q: Annotated[str, Query(min_length=1, max_length=500)],
    reranker: Annotated[CandidateReranker | None, Depends(get_reranker)],
    limit: Annotated[int, Query(ge=1, le=50)] = 10, rerank: bool = False):
    if not q.strip() or '\0' in q: raise HTTPException(422, 'Enter a query without NUL characters')
    results, retrieval = hybrid_results(workspace_id, session, q.strip(), limit, factory)
    results, ranking = rerank_candidates(q.strip(), results, reranker) if rerank else (results, 'disabled')
    return {'retrieval': retrieval, 'reranker': ranking, 'results': results}
