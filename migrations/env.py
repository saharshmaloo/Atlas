from alembic import context
from sqlalchemy import create_engine, pool

from atlas.answers import AnswerRecord  # noqa: F401 -- register model metadata
from atlas.events import RunEvent  # noqa: F401
from atlas.embeddings import EmbeddingProfile, PassageEmbedding  # noqa: F401
from atlas.database import Base, database_url
from atlas.memory import MemoryClaim, ClaimEvidence  # noqa: F401
from atlas.passages import Passage  # noqa: F401 -- register model metadata
from atlas.runs import ResearchRun, ResearchTask  # noqa: F401
from atlas.sources import Source  # noqa: F401 -- register model metadata
from atlas.verification_api import VerificationRecord  # noqa: F401
from atlas.workspaces import Workspace  # noqa: F401 -- register model metadata


url = context.config.attributes.get("database_url") or database_url()
if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
