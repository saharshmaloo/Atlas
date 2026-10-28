from types import SimpleNamespace
from uuid import uuid4

import pytest
from atlas.answers import Claim
from atlas.verification import ConservativeVerifier, verify_claims


def case():
    pid = uuid4()
    return [Claim(text='Claim', passage_ids=[pid])], [SimpleNamespace(id=pid, text='Evidence')]


def test_unconfigured_verifier_is_explicitly_uncertain():
    claims, citations = case()
    assert verify_claims(ConservativeVerifier(), 'Question', claims, citations)[0].status == 'uncertain'


@pytest.mark.parametrize('status', ['supported', 'unsupported', 'uncertain'])
def test_accepts_bounded_structured_judgments(status):
    claims, citations = case()
    verifier = SimpleNamespace(verify=lambda *args: {'judgments': [{
        'claim_index': 0, 'status': status, 'passage_ids': claims[0].passage_ids, 'explanation': 'Fallible judgment'}]})
    assert verify_claims(verifier, 'Question', claims, citations)[0].status == status


@pytest.mark.parametrize('patch', [
    {'claim_index': 1}, {'status': 'proof'}, {'passage_ids': [str(uuid4())]},
    {'passage_ids': []}, {'explanation': ''}, {'explanation': 'x\0y'},
])
def test_rejects_invalid_judgments(patch):
    claims, citations = case()
    judgment = {'claim_index': 0, 'status': 'supported', 'passage_ids': claims[0].passage_ids, 'explanation': 'Judgment'}
    verifier = SimpleNamespace(verify=lambda *args: {'judgments': [{**judgment, **patch}]})
    with pytest.raises(ValueError):
        verify_claims(verifier, 'Question', claims, citations)


def test_rejects_missing_duplicate_or_oversized_evidence():
    claims, citations = case()
    for judgments in [[], [{'claim_index': 0, 'status': 'uncertain', 'passage_ids': [], 'explanation': 'Unknown'}] * 2]:
        with pytest.raises(ValueError):
            verify_claims(SimpleNamespace(verify=lambda *args: {'judgments': judgments}), 'Q', claims, citations)
    citations[0].text = 'x' * 12001
    with pytest.raises(ValueError):
        verify_claims(ConservativeVerifier(), 'Q', claims, citations)
