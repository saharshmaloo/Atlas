"""Persist research runs and recoverable tasks."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '0012'
down_revision = '0011'
branch_labels = depends_on = None


def upgrade():
    op.create_table('research_runs',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('workspace_id', sa.Uuid(), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('objective', sa.String(500), nullable=False),
        sa.Column('status', sa.String(16), server_default='queued', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_research_runs_workspace_id', 'research_runs', ['workspace_id'])
    op.create_table('research_tasks',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('run_id', sa.Uuid(), sa.ForeignKey('research_runs.id'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False), sa.Column('kind', sa.String(16), nullable=False),
        sa.Column('question', sa.String(500), nullable=False),
        sa.Column('status', sa.String(16), server_default='queued', nullable=False),
        sa.Column('output', JSONB()), sa.Column('error', sa.String(200)))
    op.create_index('ix_research_tasks_run_id', 'research_tasks', ['run_id'])


def downgrade():
    op.drop_table('research_tasks'); op.drop_table('research_runs')
