"""Preserve original PDF bytes and extracted-page locations."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '0009'
down_revision = '0008'
branch_labels = depends_on = None


def upgrade():
    op.add_column('sources', sa.Column('locations', JSONB(), server_default='[]', nullable=False))
    op.add_column('sources', sa.Column('extractor', sa.String(32)))
    op.add_column('sources', sa.Column('original_data', sa.LargeBinary()))


def downgrade():
    for column in ['original_data', 'extractor', 'locations']:
        op.drop_column('sources', column)
