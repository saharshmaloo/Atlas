"""Retain conflicts, supersession links, and question resolution history."""
from alembic import op
import sqlalchemy as sa
revision = '0018'
down_revision = '0017'
branch_labels = depends_on = None


def upgrade():
    op.create_table('claim_relations', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('workspace_id', sa.Uuid(), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('from_claim_id', sa.Uuid(), sa.ForeignKey('memory_claims.id'), nullable=False),
        sa.Column('to_claim_id', sa.Uuid(), sa.ForeignKey('memory_claims.id'), nullable=False),
        sa.Column('kind', sa.String(16), nullable=False), sa.Column('note', sa.String(1000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_claim_relations_workspace_id', 'claim_relations', ['workspace_id'])
    op.create_table('open_questions', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('workspace_id', sa.Uuid(), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('question', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_open_questions_workspace_id', 'open_questions', ['workspace_id'])
    op.create_table('question_updates', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('question_id', sa.Uuid(), sa.ForeignKey('open_questions.id'), nullable=False),
        sa.Column('status', sa.String(16), nullable=False), sa.Column('note', sa.String(1000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.clock_timestamp(), nullable=False))
    op.create_index('ix_question_updates_question_id', 'question_updates', ['question_id'])


def downgrade():
    op.drop_table('question_updates'); op.drop_table('open_questions'); op.drop_table('claim_relations')
