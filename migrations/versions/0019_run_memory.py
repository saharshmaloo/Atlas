"""Persist opt-in memory expansion for durable investigations."""
from alembic import op
import sqlalchemy as sa
revision = '0019'
down_revision = '0018'
branch_labels = depends_on = None


def upgrade():
    op.add_column('research_runs', sa.Column('use_memory', sa.Boolean(), server_default='false', nullable=False))


def downgrade():
    op.drop_column('research_runs', 'use_memory')
