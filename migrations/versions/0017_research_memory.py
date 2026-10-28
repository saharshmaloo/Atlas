"""Atomic interpretations and immutable evidence assessments."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '0017'
down_revision = '0016'
branch_labels = depends_on = None


def upgrade():
    op.create_table('memory_claims', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('workspace_id', sa.Uuid(), sa.ForeignKey('workspaces.id'), nullable=False),
        sa.Column('answer_id', sa.Uuid(), sa.ForeignKey('answers.id'), nullable=False),
        sa.Column('claim_index', sa.Integer(), nullable=False), sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_memory_claims_workspace_id', 'memory_claims', ['workspace_id'])
    op.create_table('claim_evidence', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('claim_id', sa.Uuid(), sa.ForeignKey('memory_claims.id'), nullable=False),
        sa.Column('passage_id', sa.Uuid(), nullable=False), sa.Column('relation', sa.String(16), nullable=False),
        sa.Column('verification_status', sa.String(16), nullable=False),
        sa.Column('verification_id', sa.Uuid(), sa.ForeignKey('answer_verifications.id')),
        sa.Column('snapshot', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_claim_evidence_claim_id', 'claim_evidence', ['claim_id'])


def downgrade():
    op.drop_table('claim_evidence'); op.drop_table('memory_claims')
