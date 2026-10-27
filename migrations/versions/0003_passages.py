"""Store source passages with stable positions and exact text offsets."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "passages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.Uuid(), sa.ForeignKey("sources.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("chunker_version", sa.String(32), nullable=False),
        sa.UniqueConstraint("source_id", "position", name="passage_source_position"),
        sa.CheckConstraint("position >= 0", name="passage_position_nonnegative"),
        sa.CheckConstraint("start_char >= 0 AND end_char > start_char", name="passage_valid_span"),
        sa.CheckConstraint("char_length(text) = end_char - start_char", name="passage_text_length"),
    )


def downgrade():
    op.drop_table("passages")
