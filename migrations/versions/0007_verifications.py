"""Append-only judgments separate from original answer snapshots."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '0007'
down_revision = '0006'
branch_labels = depends_on = None


def upgrade():
    op.create_table('answer_verifications',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('answer_id', sa.Uuid(), sa.ForeignKey('answers.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('verifier', sa.String(200), nullable=False),
        sa.Column('judgments', JSONB(), nullable=False))
    op.create_index('ix_answer_verifications_answer_id', 'answer_verifications', ['answer_id'])


def downgrade():
    op.drop_table('answer_verifications')
