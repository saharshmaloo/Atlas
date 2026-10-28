from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid5
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, ForeignKey, String, Text, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Mapped, mapped_column
from atlas.answers import get_answer
from atlas.database import Base
from atlas.sources import Source, require_workspace
from atlas.passages import Passage
from atlas.verification_api import VerificationRecord
from atlas.workspaces import DatabaseSession


class MemoryClaim(Base):
    __tablename__ = 'memory_claims'
    id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey('workspaces.id'), index=True)
    answer_id: Mapped[UUID] = mapped_column(ForeignKey('answers.id'))
    claim_index: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClaimEvidence(Base):
    __tablename__ = 'claim_evidence'
    id: Mapped[UUID] = mapped_column(primary_key=True)
    claim_id: Mapped[UUID] = mapped_column(ForeignKey('memory_claims.id'), index=True)
    passage_id: Mapped[UUID]
    relation: Mapped[str] = mapped_column(String(16))
    verification_status: Mapped[str] = mapped_column(String(16))
    verification_id: Mapped[UUID | None] = mapped_column(ForeignKey('answer_verifications.id'))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    passage_id: UUID
    relation: str
    verification_status: str
    verification_id: UUID | None
    snapshot: dict
    freshness: str = 'unknown'
    created_at: datetime


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workspace_id: UUID
    answer_id: UUID
    claim_index: int
    text: str
    created_at: datetime
    kind: str = 'generated_interpretation'
    state: str = 'active'
    latest_verification_id: UUID | None = None
    relations: list[dict] = []
    evidence: list[EvidenceResponse]


def memory_response(claim, session):
    from atlas.memory_state import ClaimRelation
    from sqlalchemy import or_
    relations = list(session.scalars(select(ClaimRelation).where(ClaimRelation.workspace_id == claim.workspace_id,
        or_(ClaimRelation.from_claim_id == claim.id, ClaimRelation.to_claim_id == claim.id))
        .order_by(ClaimRelation.created_at, ClaimRelation.id)))
    latest_verification = session.scalar(select(VerificationRecord).where(VerificationRecord.answer_id == claim.answer_id)
        .order_by(VerificationRecord.created_at.desc(), VerificationRecord.id.desc()).limit(1))
    latest_id = latest_verification.id if latest_verification else None
    state = 'superseded' if any(item.kind == 'supersedes' and item.to_claim_id == claim.id for item in relations) else 'contested' if any(item.kind == 'contradicts' for item in relations) else 'active'
    relation_data = [{key: getattr(item, key) for key in ('id', 'from_claim_id', 'to_claim_id', 'kind', 'note', 'created_at')} for item in relations]
    evidence = []
    for edge in session.scalars(select(ClaimEvidence).where(ClaimEvidence.claim_id == claim.id)
            .order_by(ClaimEvidence.created_at, ClaimEvidence.id)):
        row = session.execute(select(Passage, Source).join(Source).where(
            Passage.id == edge.passage_id, Source.workspace_id == claim.workspace_id)).first()
        freshness = 'missing'
        if row:
            passage, source = row
            latest = session.scalar(select(func.max(Source.version)).where(Source.workspace_id == claim.workspace_id,
                Source.document_id == source.document_id))
            freshness = 'current' if source.version == latest and passage.text == edge.snapshot['text'] else 'superseded_source'
        evidence.append(EvidenceResponse.model_validate(edge).model_copy(update={'freshness': freshness}))
    if state == 'active' and latest_id and not any(edge.verification_id == latest_id for edge in evidence):
        state = 'assessment_outdated'
    return MemoryResponse(**{key: getattr(claim, key) for key in ('id', 'workspace_id', 'answer_id', 'claim_index', 'text', 'created_at')}, evidence=evidence, state=state, relations=relation_data, latest_verification_id=latest_id)


router = APIRouter(prefix='/workspaces/{workspace_id}', tags=['research memory'])


@router.post('/answers/{answer_id}/remember', response_model=list[MemoryResponse])
def remember_answer(workspace_id: UUID, answer_id: UUID, session: DatabaseSession, verification_id: UUID | None = None):
    answer = get_answer(workspace_id, answer_id, session)
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key': f'memory:{answer_id}'})
    query = select(VerificationRecord).where(VerificationRecord.answer_id == answer_id)
    if verification_id: query = query.where(VerificationRecord.id == verification_id)
    verification = session.scalar(query.order_by(VerificationRecord.created_at.desc(), VerificationRecord.id.desc()).limit(1))
    if verification_id and verification is None: raise HTTPException(404, 'Verification not found for this answer')
    judgments = {item['claim_index']: item for item in verification.judgments} if verification else {}
    citations = {item.id: item for item in answer.citations}
    ids = []
    for index, claim in enumerate(answer.claims):
        cid = uuid5(answer_id, f'claim:{index}'); ids.append(cid)
        session.execute(insert(MemoryClaim).values(id=cid, workspace_id=workspace_id, answer_id=answer_id,
            claim_index=index, text=claim.text).on_conflict_do_nothing())
        judgment = judgments.get(index)
        for pid in claim.passage_ids:
            judged = judgment and str(pid) in judgment['passage_ids']
            status = judgment['status'] if judged else 'uncertain'
            relation = {'supported': 'supports', 'unsupported': 'contradicts', 'uncertain': 'mentions'}[status]
            vid = verification.id if verification else None
            session.execute(insert(ClaimEvidence).values(id=uuid5(cid, f'{pid}:{vid}'), claim_id=cid,
                passage_id=pid, relation=relation, verification_status=status, verification_id=vid,
                snapshot=citations[pid].model_dump(mode='json')).on_conflict_do_nothing())
    session.commit()
    return [get_claim(workspace_id, cid, session) for cid in ids]


@router.get('/claims', response_model=list[MemoryResponse])
def list_claims(workspace_id: UUID, session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Annotated[int, Query(ge=0)] = 0):
    require_workspace(workspace_id, session)
    claims = session.scalars(select(MemoryClaim).where(MemoryClaim.workspace_id == workspace_id)
        .order_by(MemoryClaim.created_at.desc(), MemoryClaim.id.desc()).offset(offset).limit(limit))
    return [memory_response(claim, session) for claim in claims]


@router.get('/claims/{claim_id}', response_model=MemoryResponse)
def get_claim(workspace_id: UUID, claim_id: UUID, session: DatabaseSession):
    claim = session.scalar(select(MemoryClaim).where(MemoryClaim.id == claim_id, MemoryClaim.workspace_id == workspace_id))
    if claim is None: raise HTTPException(404, 'Claim not found')
    return memory_response(claim, session)
