"""Versioned passage embeddings."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '0010'
down_revision = '0009'
branch_labels = depends_on = None


def upgrade():
    op.create_table('embedding_profiles', sa.Column('id', sa.String(64), primary_key=True),
                    sa.Column('spec', JSONB(), nullable=False))
    op.create_table('passage_embeddings',
        sa.Column('passage_id', sa.Uuid(), sa.ForeignKey('passages.id'), primary_key=True),
        sa.Column('profile_id', sa.String(64), sa.ForeignKey('embedding_profiles.id'), primary_key=True),
        sa.Column('dimensions', sa.Integer(), nullable=False), sa.Column('vector', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('jsonb_array_length(vector) = dimensions', name='embedding_dimensions'))


def downgrade():
    op.drop_table('passage_embeddings'); op.drop_table('embedding_profiles')
