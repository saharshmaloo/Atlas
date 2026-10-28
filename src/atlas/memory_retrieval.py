from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import exists, func, select
from atlas.memory_state import ClaimRelation
from atlas.memory import MemoryClaim, memory_response
from atlas.search import SearchResult
from atlas.sources import require_workspace
from atlas.workspaces import DatabaseSession


def retrieve_memory(workspace_id, session, q, limit):
    require_workspace(workspace_id, session)
    query = func.websearch_to_tsquery('english', q)
    vector = func.to_tsvector('english', MemoryClaim.text)
    claims = session.scalars(select(MemoryClaim).where(MemoryClaim.workspace_id == workspace_id,
        vector.bool_op('@@')(query), ~exists(select(ClaimRelation.id).where(ClaimRelation.to_claim_id == MemoryClaim.id, ClaimRelation.kind == 'supersedes'))).order_by(func.ts_rank_cd(vector, query).desc(), MemoryClaim.id).limit(limit))
    return [memory_response(claim, session) for claim in claims]


def memory_passages(workspace_id, session, q, limit):
    """Reuse current original evidence only; never supply generated claims as source text."""
    results, seen = [], set()
    for claim in retrieve_memory(workspace_id, session, q, 20):
        if claim.state != 'active': continue
        latest = {item.passage_id: item for item in claim.evidence}
        for edge in latest.values():
            if edge.verification_status != 'supported' or edge.freshness != 'current' or edge.passage_id in seen: continue
            results.append(SearchResult.model_validate(edge.snapshot))
            seen.add(edge.passage_id)
            if len(results) >= limit: return results
    return results


router = APIRouter(prefix='/workspaces/{workspace_id}', tags=['memory retrieval'])


@router.get('/memory-search')
def search_memory(workspace_id: UUID, session: DatabaseSession,
    q: Annotated[str, Query(min_length=1, max_length=500)], limit: Annotated[int, Query(ge=1, le=50)] = 10):
    if not q.strip() or '\0' in q: raise HTTPException(422, 'Enter a query without NUL characters')
    return retrieve_memory(workspace_id, session, q.strip(), limit)
