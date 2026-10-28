from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, select, text
from atlas.embeddings import (EmbeddingError, EmbeddingProfile, EmbeddingProvider, PassageEmbedding,
                              embed_batch, get_embedding_provider, store_vectors)
from atlas.passages import Passage
from atlas.sources import Source, require_workspace
from atlas.workspaces import DatabaseSession

router = APIRouter(prefix='/workspaces/{workspace_id}/embeddings', tags=['embeddings'])


def embedding_status(workspace_id, profile_id, session):
    require_workspace(workspace_id, session)
    profile = session.get(EmbeddingProfile, profile_id)
    if profile is None: raise HTTPException(404, 'Embedding profile not found')
    scope = select(Passage.id).join(Source).where(Source.workspace_id == workspace_id)
    total = session.scalar(select(func.count()).select_from(scope.subquery()))
    complete = session.scalar(select(func.count()).select_from(PassageEmbedding).where(
        PassageEmbedding.profile_id == profile_id, PassageEmbedding.passage_id.in_(scope)))
    return {'profile_id': profile_id, 'spec': profile.spec, 'total': total, 'embedded': complete,
            'remaining': total - complete, 'complete': total == complete}


@router.get('/{profile_id}')
def get_embedding_status(workspace_id: UUID, profile_id: str, session: DatabaseSession):
    return embedding_status(workspace_id, profile_id, session)


@router.post('')
def generate_embeddings(workspace_id: UUID, session: DatabaseSession,
    provider: Annotated[EmbeddingProvider, Depends(get_embedding_provider)],
    batch_size: Annotated[int, Query(ge=1, le=16)] = 16,
    max_batches: Annotated[int, Query(ge=1, le=4)] = 1):
    require_workspace(workspace_id, session)
    spec = provider.spec
    for _ in range(max_batches):
        session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'),
                        {'key': f'embedding:{workspace_id}:{spec.id}'})
        pending = list(session.scalars(select(Passage).join(Source).where(Source.workspace_id == workspace_id,
            ~exists(select(PassageEmbedding.passage_id).where(PassageEmbedding.passage_id == Passage.id,
                PassageEmbedding.profile_id == spec.id))).order_by(Passage.source_id, Passage.position).limit(batch_size)))
        try:
            vectors = embed_batch(provider, [item.text for item in pending]) if pending else []
            store_vectors(session, spec, [item.id for item in pending], vectors)
            session.commit()  # Completed batches survive a later failure and resume without duplicates.
        except (EmbeddingError, TimeoutError):
            session.rollback()
            raise HTTPException(502, 'Embedding batch failed; completed batches are retained for retry') from None
        if len(pending) < batch_size: break
    return embedding_status(workspace_id, spec.id, session)
