"""Transactional ordered operational events."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '0016'
down_revision = '0015'
branch_labels = depends_on = None


def upgrade():
    op.add_column('research_runs', sa.Column('event_seq', sa.Integer(), server_default='0', nullable=False))
    op.create_table('research_events',
        sa.Column('run_id', sa.Uuid(), sa.ForeignKey('research_runs.id'), primary_key=True),
        sa.Column('sequence', sa.Integer(), primary_key=True),
        sa.Column('task_id', sa.Uuid(), sa.ForeignKey('research_tasks.id')),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp(), nullable=False),
        sa.Column('data', JSONB(), nullable=False))


def downgrade():
    op.drop_table('research_events'); op.drop_column('research_runs', 'event_seq')
