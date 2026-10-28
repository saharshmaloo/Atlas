"""Include retrieval configuration in request-key content identity."""
from alembic import op
import sqlalchemy as sa
revision = '0011'
down_revision = '0010'
branch_labels = depends_on = None


def upgrade():
    op.add_column('answer_submissions', sa.Column('request_hash', sa.String(64)))


def downgrade():
    op.drop_column('answer_submissions', 'request_hash')
