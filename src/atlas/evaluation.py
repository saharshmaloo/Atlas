"""Small deterministic metrics; labels are human judgments, never model truth."""
from math import log2


def retrieval_metrics(cases):
    """cases: (ranked unique IDs, relevant IDs); empty labels test abstention."""
    recall, reciprocal, ndcg, empty = [], [], [], []
    for ranked, labels in cases:
        relevant = set(labels)
        ranked = list(dict.fromkeys(ranked))
        if not relevant:
            empty.append(float(not ranked))
            continue
        hits = [int(item in relevant) for item in ranked]
        recall.append(sum(hits) / len(relevant))
        reciprocal.append(next((1 / (i + 1) for i, hit in enumerate(hits) if hit), 0))
        dcg = sum(hit / log2(i + 2) for i, hit in enumerate(hits))
        ideal = sum(1 / log2(i + 2) for i in range(min(len(ranked), len(relevant))))
        ndcg.append(dcg / ideal if ideal else 0)
    mean = lambda values: sum(values) / len(values) if values else None
    return {'recall': mean(recall), 'mrr': mean(reciprocal), 'ndcg': mean(ndcg),
            'empty_query_accuracy': mean(empty)}


def grounding_metrics(cases):
    """Keep citation membership, support classification, and abstention separate."""
    labeled = [case for case in cases if case['expected_support'] is not None]
    supported = [case for case in labeled if case['predicted_support'] == 'supported']
    return {
        'citation_membership': sum(case['citations_valid'] for case in cases) / len(cases) if cases else None,
        'support_accuracy': sum(case['predicted_support'] == case['expected_support'] for case in labeled) / len(labeled) if labeled else None,
        'false_support_rate': sum(case['expected_support'] != 'supported' for case in supported) / len(supported) if supported else None,
        'abstention_accuracy': sum(case['abstained'] == case['expected_abstain'] for case in cases) / len(cases) if cases else None,
    }
