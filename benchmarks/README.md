# Evaluation corpus

`retrieval-v1.json` is a synthetic, versioned corpus with manually specified source relevance. Run `TEST_DATABASE_URL=... python -m pytest tests/test_evaluation.py -q -W error` against PostgreSQL 17. Each test builds a disposable database, ingests the exact texts, generates passages, and searches the labeled queries at k=5.

Keyword baseline: recall@5 = 0.8, MRR@5 = 0.8, nDCG@5 = 0.8; empty-query accuracy = 1.0. The intentionally missed synonym case exposes a keyword limitation. This tiny fixture checks regressions; it does not establish general research quality. Source-level relevance works here because every fixture has one passage. Expand labels at passage level for larger corpora. No production data or paid calls are used.
