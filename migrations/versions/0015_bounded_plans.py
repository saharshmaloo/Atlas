"""Ordered task dependencies, planner provenance, and idempotent verification effects."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '0015'
down_revision = '0014'
branch_labels = depends_on = None


def upgrade():
    op.add_column('research_runs', sa.Column('plan_version', sa.String(100)))
    op.add_column('research_tasks', sa.Column('depends_on', JSONB(), server_default='[]', nullable=False))
    op.add_column('answer_verifications', sa.Column('request_key', sa.String(64)))
    op.create_unique_constraint('uq_verification_request_key', 'answer_verifications', ['request_key'])


def downgrade():
    op.drop_column('answer_verifications', 'request_key')
    op.drop_column('research_tasks', 'depends_on'); op.drop_column('research_runs', 'plan_version')
