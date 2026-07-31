"""Add script version history

Revision ID: e91c6b07842a
Revises: d4f2b8a71c09
Create Date: 2026-07-25 04:05:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e91c6b07842a"
down_revision = "d4f2b8a71c09"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workbench_generated_script", sa.Column("version_history", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("workbench_generated_script", "version_history")
