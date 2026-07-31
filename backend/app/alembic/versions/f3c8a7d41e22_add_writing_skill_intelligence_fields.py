"""Add writing Skill intelligence and source merge fields.

Revision ID: f3c8a7d41e22
Revises: e91c6b07842a
Create Date: 2026-07-27 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "f3c8a7d41e22"
down_revision = "e91c6b07842a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workbench_template_pattern", sa.Column("solves_problems", sa.JSON(), nullable=True))
    op.add_column("workbench_template_pattern", sa.Column("match_signals", sa.JSON(), nullable=True))
    op.add_column("workbench_template_pattern", sa.Column("source_titles", sa.JSON(), nullable=True))
    op.add_column(
        "workbench_template_pattern",
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "workbench_template_pattern",
        sa.Column("pattern_fingerprint", sa.String(length=40), nullable=True),
    )
    op.create_index(
        op.f("ix_workbench_template_pattern_pattern_fingerprint"),
        "workbench_template_pattern",
        ["pattern_fingerprint"],
        unique=False,
    )
    op.alter_column("workbench_template_pattern", "source_count", server_default=None)


def downgrade():
    op.drop_index(
        op.f("ix_workbench_template_pattern_pattern_fingerprint"),
        table_name="workbench_template_pattern",
    )
    op.drop_column("workbench_template_pattern", "pattern_fingerprint")
    op.drop_column("workbench_template_pattern", "source_count")
    op.drop_column("workbench_template_pattern", "source_titles")
    op.drop_column("workbench_template_pattern", "match_signals")
    op.drop_column("workbench_template_pattern", "solves_problems")
