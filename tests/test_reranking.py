from types import SimpleNamespace
import pytest
from atlas.evaluation import retrieval_metrics
from atlas.reranking import LexicalReranker, rerank_candidates


def test_optional_reranker_improves_labeled_order_without_changing_membership():
    candidates = [SimpleNamespace(id='wrong', text='Logs use storage.'), SimpleNamespace(id='right', text='Transactions are durable.')]
    result, identity = rerank_candidates('durable transactions', candidates, LexicalReranker())
    assert identity == 'lexical-overlap-v1'
    before = retrieval_metrics([([x.id for x in candidates], ['right'])])
    after = retrieval_metrics([([x.id for x in result], ['right'])])
    assert before['mrr'] == .5 and after['mrr'] == 1
    assert before['recall'] == after['recall'] == 1


@pytest.mark.parametrize('order', [[], ['other'], ['a', 'a']])
def test_invalid_rankings_fall_back_without_losing_evidence(order):
    items = [SimpleNamespace(id='a', text='Evidence'), SimpleNamespace(id='b', text='Evidence')]
    result, status = rerank_candidates('query', items, SimpleNamespace(rank=lambda *args: order, identity='fake'))
    assert result is items and status == 'fallback'


def test_timeout_and_unconfigured_rerankers_preserve_order():
    items = [SimpleNamespace(id='a', text='Evidence')]
    def timeout(*args): raise TimeoutError()
    assert rerank_candidates('q', items, SimpleNamespace(rank=timeout))[1] == 'fallback'
    assert rerank_candidates('q', items, None) == (items, 'unconfigured')
