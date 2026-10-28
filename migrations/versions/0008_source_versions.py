"""Immutable source identities and provenance."""
from alembic import op
import sqlalchemy as sa
revision = '0008'
down_revision = '0007'
branch_labels = depends_on = None


def upgrade():
    op.add_column('sources', sa.Column('document_id', sa.Uuid(), nullable=True))
    op.execute('UPDATE sources SET document_id = id')
    op.alter_column('sources', 'document_id', nullable=False)
    op.add_column('sources', sa.Column('version', sa.Integer(), server_default='1', nullable=False))
    op.add_column('sources', sa.Column('kind', sa.String(16), server_default='text', nullable=False))
    op.add_column('sources', sa.Column('original_uri', sa.String(2048)))
    op.add_column('sources', sa.Column('retrieved_at', sa.DateTime(timezone=True)))
    op.create_unique_constraint('source_document_version', 'sources', ['workspace_id', 'document_id', 'version'])


def downgrade():
    op.drop_constraint('source_document_version', 'sources')
    for column in ['retrieved_at', 'original_uri', 'kind', 'version', 'document_id']:
        op.drop_column('sources', column)
