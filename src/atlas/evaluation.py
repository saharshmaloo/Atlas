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
