"""Index existing and future passage text for keyword retrieval."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("passages", sa.Column(
        "search_vector", postgresql.TSVECTOR(),
        sa.Computed("to_tsvector('english'::regconfig, text)", persisted=True), nullable=False,
    ))
    op.create_index("ix_passages_search_vector", "passages", ["search_vector"], postgresql_using="gin")


def downgrade():
    op.drop_index("ix_passages_search_vector", table_name="passages")
    op.drop_column("passages", "search_vector")
