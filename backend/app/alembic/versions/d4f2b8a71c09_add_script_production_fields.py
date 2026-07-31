"""Add script production fields

Revision ID: d4f2b8a71c09
Revises: b6a94e2c1f2a
Create Date: 2026-07-25 03:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d4f2b8a71c09"
down_revision = "b6a94e2c1f2a"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workbench_generated_script",
        sa.Column("production_status", sa.String(length=32), nullable=False, server_default="draft"),
    )
    op.add_column(
        "workbench_generated_script",
        sa.Column("version_label", sa.String(length=40), nullable=False, server_default="v1"),
    )
    op.add_column("workbench_generated_script", sa.Column("editor_note", sa.String(), nullable=True))
    op.add_column("workbench_generated_script", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        op.f("ix_workbench_generated_script_production_status"),
        "workbench_generated_script",
        ["production_status"],
        unique=False,
    )
    op.alter_column("workbench_generated_script", "production_status", server_default=None)
    op.alter_column("workbench_generated_script", "version_label", server_default=None)


def downgrade():
    op.drop_index(op.f("ix_workbench_generated_script_production_status"), table_name="workbench_generated_script")
    op.drop_column("workbench_generated_script", "updated_at")
    op.drop_column("workbench_generated_script", "editor_note")
    op.drop_column("workbench_generated_script", "version_label")
    op.drop_column("workbench_generated_script", "production_status")
