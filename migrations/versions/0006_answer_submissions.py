"""Workspace-scoped atomic answer request keys."""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = depends_on = None


def upgrade():
    op.create_table('answer_submissions',
        sa.Column('workspace_id', sa.Uuid(), sa.ForeignKey('workspaces.id'), primary_key=True),
        sa.Column('key', sa.String(128), primary_key=True),
        sa.Column('question', sa.String(500), nullable=False),
        sa.Column('answer_id', sa.Uuid(), sa.ForeignKey('answers.id'), nullable=False))


def downgrade():
    op.drop_table('answer_submissions')
