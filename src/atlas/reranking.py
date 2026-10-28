import os
import re
from typing import Protocol


class CandidateReranker(Protocol):
    identity: str
    def rank(self, query, candidates): ...


class RerankerError(Exception): pass


class LexicalReranker:
    """Cheap optional baseline; term overlap is not a semantic judgment."""
    identity = 'lexical-overlap-v1'
    def rank(self, query, candidates):
        terms = set(re.findall(r'\w+', query.lower()))
        ordered = sorted(enumerate(candidates), key=lambda pair:
            (-len(terms & set(re.findall(r'\w+', pair[1].text.lower()))), pair[0]))
        return [item.id for _, item in ordered]


def get_reranker() -> CandidateReranker | None:
    return LexicalReranker() if os.getenv('ATLAS_RERANKER') == 'lexical-v1' else None


def rerank_candidates(query, candidates, reranker):
    if reranker is None: return candidates, 'unconfigured'
    if len(candidates) > 50 or len(query) > 500: raise ValueError('Reranking input exceeds bounds')
    try:
        order = list(reranker.rank(query, candidates))
        lookup = {item.id: item for item in candidates}
        if len(order) != len(candidates) or set(order) != set(lookup): raise RerankerError()
        return [lookup[pid] for pid in order], reranker.identity
    except (RerankerError, TimeoutError, TypeError, ValueError):
        return candidates, 'fallback'
