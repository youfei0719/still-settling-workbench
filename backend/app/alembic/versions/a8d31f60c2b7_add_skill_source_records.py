"""Add traceable source records to writing Skills.

Revision ID: a8d31f60c2b7
Revises: f3c8a7d41e22
Create Date: 2026-07-27 15:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a8d31f60c2b7"
down_revision = "f3c8a7d41e22"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workbench_template_pattern",
        sa.Column("sources", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("workbench_template_pattern", "sources")
