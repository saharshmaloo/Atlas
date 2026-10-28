"""Durable conservative research execution budgets."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '0014'
down_revision = '0013'
branch_labels = depends_on = None
DEFAULT = '{"max_attempts":3,"max_concurrency":1,"max_model_calls":3,"max_tool_calls":8,"max_seconds":300,"max_model_tokens":500000}'


def upgrade():
    op.add_column('research_runs', sa.Column('budgets', JSONB(), nullable=True))
    op.execute(sa.text('UPDATE research_runs SET budgets = CAST(:value AS jsonb)').bindparams(value=DEFAULT))
    op.alter_column('research_runs', 'budgets', nullable=False)
    for field in ['model_calls_reserved', 'tool_calls', 'tokens_reserved']:
        op.add_column('research_runs', sa.Column(field, sa.Integer(), server_default='0', nullable=False))
    for field in ['started_at', 'deadline_at']:
        op.add_column('research_runs', sa.Column(field, sa.DateTime(timezone=True)))


def downgrade():
    for field in ['deadline_at', 'started_at', 'tokens_reserved', 'tool_calls', 'model_calls_reserved', 'budgets']:
        op.drop_column('research_runs', field)
