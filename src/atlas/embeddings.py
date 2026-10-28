from datetime import datetime
from hashlib import sha256
import math
import os
from typing import Protocol
from uuid import UUID

from fastapi import HTTPException
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Mapped, mapped_column
from atlas.database import Base


class EmbeddingSpec(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    dimensions: int = Field(ge=1, le=4096)

    @property
    def id(self):
        return sha256(self.model_dump_json().encode()).hexdigest()


class EmbeddingProfile(Base):
    __tablename__ = 'embedding_profiles'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    spec: Mapped[dict] = mapped_column(JSONB)


class PassageEmbedding(Base):
    __tablename__ = 'passage_embeddings'
    __table_args__ = (CheckConstraint('jsonb_array_length(vector) = dimensions', name='embedding_dimensions'),)
    passage_id: Mapped[UUID] = mapped_column(ForeignKey('passages.id'), primary_key=True)
    profile_id: Mapped[str] = mapped_column(ForeignKey('embedding_profiles.id'), primary_key=True)
    dimensions: Mapped[int]
    vector: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmbeddingProvider(Protocol):
    spec: EmbeddingSpec
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingError(Exception): pass


def normalized(vector, dimensions):
    if len(vector) != dimensions or any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in vector):
        raise EmbeddingError('Invalid embedding vector')
    norm = math.hypot(*vector)
    if not norm or not math.isfinite(norm):
        raise EmbeddingError('Invalid embedding norm')
    return [x / norm for x in vector]


def embed_batch(provider, texts):
    if not 0 < len(texts) <= 16 or any(not t.strip() or len(t) > 1000 for t in texts):
        raise EmbeddingError('Embedding input exceeds bounds')
    vectors = provider.embed(texts)
    if len(vectors) != len(texts):
        raise EmbeddingError('Embedding response count mismatch')
    return [normalized(vector, provider.spec.dimensions) for vector in vectors]


def store_vectors(session, spec, passage_ids, vectors):
    if len(passage_ids) != len(vectors): raise EmbeddingError('Embedding count mismatch')
    session.execute(insert(EmbeddingProfile).values(id=spec.id, spec=spec.model_dump()).on_conflict_do_nothing())
    for pid, vector in zip(passage_ids, vectors):
        session.execute(insert(PassageEmbedding).values(passage_id=pid, profile_id=spec.id,
            dimensions=spec.dimensions, vector=normalized(vector, spec.dimensions)).on_conflict_do_nothing())


class OpenAIEmbeddings:
    def __init__(self, spec, key): self.spec, self.key = spec, key

    def embed(self, texts):
        try:
            with OpenAI(api_key=self.key, timeout=30, max_retries=0) as client:
                result = client.embeddings.create(model=self.spec.model, input=texts,
                    dimensions=self.spec.dimensions, encoding_format='float')
            items = sorted(result.data, key=lambda item: item.index)
            if [item.index for item in items] != list(range(len(texts))): raise EmbeddingError()
            return [item.embedding for item in items]
        except OpenAIError:
            raise EmbeddingError('Embedding provider failed') from None


def get_embedding_provider() -> EmbeddingProvider:
    key, model = os.getenv('OPENAI_API_KEY'), os.getenv('ATLAS_EMBEDDING_MODEL')
    if not key or not model: raise HTTPException(503, 'Embedding provider is not configured')
    try:
        spec = EmbeddingSpec(provider='openai', model=model, version=os.getenv('ATLAS_EMBEDDING_VERSION', '1'),
                             dimensions=int(os.getenv('ATLAS_EMBEDDING_DIMENSIONS', '1536')))
    except ValueError:
        raise HTTPException(503, 'Invalid embedding configuration') from None
    return OpenAIEmbeddings(spec, key)
