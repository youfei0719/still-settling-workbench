"""Add template quality fields

Revision ID: b6a94e2c1f2a
Revises: 7c2d8f31a9b4
Create Date: 2026-07-25 02:45:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b6a94e2c1f2a"
down_revision = "7c2d8f31a9b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workbench_template_pattern", sa.Column("applicable_scenes", sa.JSON(), nullable=True))
    op.add_column("workbench_template_pattern", sa.Column("unsuitable_scenes", sa.JSON(), nullable=True))
    op.add_column("workbench_template_pattern", sa.Column("quality_score", sa.Integer(), nullable=False, server_default="80"))
    op.add_column("workbench_template_pattern", sa.Column("disabled_reason", sa.String(), nullable=True))
    op.add_column("workbench_template_pattern", sa.Column("last_review_note", sa.String(), nullable=True))
    op.create_index(
        op.f("ix_workbench_template_pattern_quality_score"),
        "workbench_template_pattern",
        ["quality_score"],
        unique=False,
    )
    op.alter_column("workbench_template_pattern", "quality_score", server_default=None)


def downgrade():
    op.drop_index(op.f("ix_workbench_template_pattern_quality_score"), table_name="workbench_template_pattern")
    op.drop_column("workbench_template_pattern", "last_review_note")
    op.drop_column("workbench_template_pattern", "disabled_reason")
    op.drop_column("workbench_template_pattern", "quality_score")
    op.drop_column("workbench_template_pattern", "unsuitable_scenes")
    op.drop_column("workbench_template_pattern", "applicable_scenes")
