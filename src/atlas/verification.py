"""Verification is a separate fallible judgment, never evidence or proof."""
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError


class Judgment(BaseModel):
    claim_index: int = Field(ge=0, lt=10)
    status: Literal['supported', 'unsupported', 'uncertain']
    passage_ids: list[UUID] = Field(max_length=5)
    explanation: str = Field(min_length=1, max_length=1000)


class VerificationDraft(BaseModel):
    judgments: list[Judgment] = Field(max_length=10)


class ClaimVerifier(Protocol):
    identity: str
    def verify(self, question, claims, citations) -> VerificationDraft: ...


class ConservativeVerifier:
    identity = 'unconfigured-v1'

    def verify(self, question, claims, citations):
        return VerificationDraft(judgments=[Judgment(
            claim_index=i, status='uncertain', passage_ids=[],
            explanation='No semantic verifier configured; citation membership alone is insufficient.',
        ) for i in range(len(claims))])


def get_claim_verifier() -> ClaimVerifier:
    return ConservativeVerifier()


def verify_claims(verifier, question, claims, citations):
    if len(claims) > 10 or len(citations) > 5 or sum(len(c.text) for c in citations) > 12000:
        raise ValueError('Verification evidence exceeds bounds')
    available = {c.id for c in citations}
    try:
        result = VerificationDraft.model_validate(verifier.verify(question, claims, citations))
    except ValidationError:
        raise ValueError('Invalid verifier response') from None
    indices = [item.claim_index for item in result.judgments]
    if sorted(indices) != list(range(len(claims))):
        raise ValueError('Verifier must judge every claim exactly once')
    for item in result.judgments:
        allowed = set(claims[item.claim_index].passage_ids) & available
        if not set(item.passage_ids) <= allowed or (item.status != 'uncertain' and not item.passage_ids):
            raise ValueError('Invalid verification evidence references')
        if '\0' in item.explanation:
            raise ValueError('Invalid verification explanation')
    return sorted(result.judgments, key=lambda item: item.claim_index)
