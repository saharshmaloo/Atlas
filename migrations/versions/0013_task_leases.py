"""Durable task leases and fencing tokens."""
from alembic import op
import sqlalchemy as sa
revision = '0013'
down_revision = '0012'
branch_labels = depends_on = None


def upgrade():
    op.add_column('research_tasks', sa.Column('attempt', sa.Integer(), server_default='0', nullable=False))
    op.add_column('research_tasks', sa.Column('lease_token', sa.Uuid()))
    op.add_column('research_tasks', sa.Column('lease_until', sa.DateTime(timezone=True)))


def downgrade():
    for column in ['lease_until', 'lease_token', 'attempt']: op.drop_column('research_tasks', column)
