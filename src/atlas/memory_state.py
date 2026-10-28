from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4, uuid5
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import DateTime, ForeignKey, String, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, mapped_column
from atlas.database import Base
from atlas.memory import MemoryClaim
from atlas.sources import require_workspace
from atlas.workspaces import DatabaseSession


class ClaimRelation(Base):
    __tablename__ = 'claim_relations'
    id: Mapped[UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey('workspaces.id'), index=True)
    from_claim_id: Mapped[UUID] = mapped_column(ForeignKey('memory_claims.id'))
    to_claim_id: Mapped[UUID] = mapped_column(ForeignKey('memory_claims.id'))
    kind: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OpenQuestion(Base):
    __tablename__ = 'open_questions'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey('workspaces.id'), index=True)
    question: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QuestionUpdate(Base):
    __tablename__ = 'question_updates'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(ForeignKey('open_questions.id'), index=True)
    status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())


class RelationRequest(BaseModel):
    from_claim_id: UUID
    to_claim_id: UUID
    kind: Literal['contradicts', 'supersedes']
    note: str = Field(min_length=1, max_length=1000)

    @field_validator('note')
    @classmethod
    def valid_note(cls, value):
        if not value.strip() or '\0' in value: raise ValueError('Enter a note without NUL characters')
        return value.strip()


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)

    @field_validator('question')
    @classmethod
    def valid_question(cls, value):
        return RelationRequest.valid_note(value)


class UpdateRequest(BaseModel):
    status: Literal['open', 'resolved']
    note: str = Field(min_length=1, max_length=1000)

    @field_validator('note')
    @classmethod
    def valid_note(cls, value):
        return RelationRequest.valid_note(value)


router = APIRouter(prefix='/workspaces/{workspace_id}', tags=['memory relationships'])


@router.post('/claim-relations', status_code=201)
def relate_claims(workspace_id: UUID, body: RelationRequest, session: DatabaseSession):
    require_workspace(workspace_id, session)
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key': f'relations:{workspace_id}'})
    ids = set(session.scalars(select(MemoryClaim.id).where(MemoryClaim.workspace_id == workspace_id,
        MemoryClaim.id.in_([body.from_claim_id, body.to_claim_id]))))
    if ids != {body.from_claim_id, body.to_claim_id}: raise HTTPException(404, 'Claim not found')
    if body.from_claim_id == body.to_claim_id: raise HTTPException(422, 'A claim cannot relate to itself')
    if body.kind == 'supersedes':
        edges = session.execute(select(ClaimRelation.from_claim_id, ClaimRelation.to_claim_id).where(
            ClaimRelation.workspace_id == workspace_id, ClaimRelation.kind == 'supersedes').limit(1001)).all()
        if len(edges) > 1000: raise HTTPException(422, 'Relationship graph exceeds local validation limit')
        frontier, visited = [body.to_claim_id], set()
        while frontier:
            item = frontier.pop()
            if item == body.from_claim_id: raise HTTPException(409, 'Supersession would create a cycle')
            if item in visited: continue
            visited.add(item); frontier.extend(target for source, target in edges if source == item)
    source, target = body.from_claim_id, body.to_claim_id
    if body.kind == 'contradicts': source, target = sorted([source, target])
    rid = uuid5(source, f'{body.kind}:{target}')
    session.execute(insert(ClaimRelation).values(id=rid, workspace_id=workspace_id, from_claim_id=source,
        to_claim_id=target, kind=body.kind, note=body.note).on_conflict_do_nothing())
    session.commit()
    return session.get(ClaimRelation, rid)


def question_response(question, session):
    updates = list(session.scalars(select(QuestionUpdate).where(QuestionUpdate.question_id == question.id)
        .order_by(QuestionUpdate.created_at, QuestionUpdate.id)))
    return {'id': question.id, 'question': question.question, 'created_at': question.created_at,
            'status': updates[-1].status if updates else 'open', 'updates': updates}


@router.post('/questions', status_code=201)
def create_question(workspace_id: UUID, body: QuestionRequest, session: DatabaseSession):
    require_workspace(workspace_id, session)
    question = OpenQuestion(workspace_id=workspace_id, question=body.question)
    session.add(question); session.commit(); session.refresh(question)
    return question_response(question, session)


@router.get('/questions')
def list_questions(workspace_id: UUID, session: DatabaseSession, offset: Annotated[int, Query(ge=0)] = 0):
    require_workspace(workspace_id, session)
    questions = session.scalars(select(OpenQuestion).where(OpenQuestion.workspace_id == workspace_id)
        .order_by(OpenQuestion.created_at.desc(), OpenQuestion.id.desc()).offset(offset).limit(50))
    return [question_response(question, session) for question in questions]


@router.post('/questions/{question_id}/updates', status_code=201)
def update_question(workspace_id: UUID, question_id: UUID, body: UpdateRequest, session: DatabaseSession):
    question = session.scalar(select(OpenQuestion).where(OpenQuestion.id == question_id,
        OpenQuestion.workspace_id == workspace_id).with_for_update())
    if question is None: raise HTTPException(404, 'Question not found')
    session.add(QuestionUpdate(question_id=question.id, status=body.status, note=body.note))
    session.commit()
    return question_response(question, session)
