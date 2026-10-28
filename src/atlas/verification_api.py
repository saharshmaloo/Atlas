from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, ForeignKey, String, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from atlas.answers import get_answer
from atlas.database import Base
from atlas.verification import ClaimVerifier, Judgment, get_claim_verifier, verify_claims
from atlas.workspaces import DatabaseSession


class VerificationRecord(Base):
    __tablename__ = 'answer_verifications'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    answer_id: Mapped[UUID] = mapped_column(ForeignKey('answers.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    verifier: Mapped[str] = mapped_column(String(200))
    judgments: Mapped[list] = mapped_column(JSONB)


class VerificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    answer_id: UUID
    created_at: datetime
    verifier: str
    judgments: list[Judgment]


router = APIRouter(prefix='/workspaces/{workspace_id}/answers/{answer_id}/verifications', tags=['verification'])


@router.post('', response_model=VerificationResponse, status_code=201)
def check_support(workspace_id: UUID, answer_id: UUID, session: DatabaseSession,
                  verifier: Annotated[ClaimVerifier, Depends(get_claim_verifier)]):
    answer = get_answer(workspace_id, answer_id, session)
    session.rollback()
    try:
        judgments = verify_claims(verifier, answer.question, answer.claims, answer.citations)
    except (ValueError, TimeoutError):
        raise HTTPException(502, 'Claim verification failed; original answer is unchanged') from None
    identity = verifier.identity
    if not identity or len(identity) > 200 or '\0' in identity:
        raise HTTPException(502, 'Invalid verifier identity')
    record = VerificationRecord(answer_id=answer_id, verifier=identity,
                                judgments=[item.model_dump(mode='json') for item in judgments])
    session.add(record); session.commit(); session.refresh(record)
    return record


@router.get('', response_model=list[VerificationResponse])
def list_verifications(workspace_id: UUID, answer_id: UUID, session: DatabaseSession):
    get_answer(workspace_id, answer_id, session)
    return list(session.scalars(select(VerificationRecord).where(VerificationRecord.answer_id == answer_id)
        .order_by(VerificationRecord.created_at.desc(), VerificationRecord.id.desc()).limit(20)))
