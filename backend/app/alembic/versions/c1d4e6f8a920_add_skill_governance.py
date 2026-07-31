"""Add governed writing Skill lifecycle, evidence, evaluations, and reviews.

Revision ID: c1d4e6f8a920
Revises: a8d31f60c2b7
Create Date: 2026-07-31 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


revision = "c1d4e6f8a920"
down_revision = "a8d31f60c2b7"
branch_labels = None
depends_on = None


def upgrade():
    table = "workbench_template_pattern"
    op.add_column(table, sa.Column("status", sa.String(length=20), nullable=False, server_default="candidate"))
    op.add_column(table, sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(table, sa.Column("owner", sa.String(length=120), nullable=False, server_default="内容主审"))
    op.add_column(table, sa.Column("platforms", sa.JSON(), nullable=True))
    op.add_column(table, sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table, sa.Column("required_inputs", sa.JSON(), nullable=True))
    op.add_column(table, sa.Column("output_contract", sa.JSON(), nullable=True))
    op.add_column(table, sa.Column("promotion_reason", sa.Text(), nullable=True))
    op.add_column(table, sa.Column("evaluation_summary", sa.JSON(), nullable=True))
    op.create_index(op.f("ix_workbench_template_pattern_status"), table, ["status"], unique=False)
    # Existing enabled records are intentionally demoted to candidate; paused records retain their boundary.
    op.execute("UPDATE workbench_template_pattern SET status = CASE WHEN disabled_reason IS NULL THEN 'candidate' ELSE 'paused' END")
    op.alter_column(table, "status", server_default=None)
    op.alter_column(table, "version", server_default=None)
    op.alter_column(table, "owner", server_default=None)

    op.create_table(
        "workbench_skill_evidence",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("template_id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("source_title", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column("source_url", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column("source_type", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("evidence_tier", sqlmodel.sql.sqltypes.AutoString(length=4), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("scope", sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["workbench_template_pattern.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workbench_skill_evidence_template_id"), "workbench_skill_evidence", ["template_id"], unique=False)

    for name in ("evaluation", "review"):
        columns = [
            sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
            sa.Column("template_id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
        ]
        if name == "evaluation":
            columns += [
                sa.Column("suite", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
                sa.Column("model_config", sa.JSON(), nullable=True),
                sa.Column("result", sa.JSON(), nullable=True),
                sa.Column("passed", sa.Boolean(), nullable=False),
                sa.Column("report_path", sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
            ]
        else:
            columns += [
                sa.Column("reviewer", sqlmodel.sql.sqltypes.AutoString(length=120), nullable=False),
                sa.Column("blind_label", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
                sa.Column("scores", sa.JSON(), nullable=True),
                sa.Column("approved", sa.Boolean(), nullable=False),
                sa.Column("note", sa.Text(), nullable=False),
            ]
        columns += [
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["template_id"], ["workbench_template_pattern.id"]),
            sa.PrimaryKeyConstraint("id"),
        ]
        op.create_table(f"workbench_skill_{name}", *columns)
        op.create_index(op.f(f"ix_workbench_skill_{name}_template_id"), f"workbench_skill_{name}", ["template_id"], unique=False)
        op.create_index(op.f(f"ix_workbench_skill_{name}_{'passed' if name == 'evaluation' else 'approved'}"), f"workbench_skill_{name}", ["passed" if name == "evaluation" else "approved"], unique=False)


def downgrade():
    for name, indexed in (("evaluation", "passed"), ("review", "approved")):
        op.drop_index(op.f(f"ix_workbench_skill_{name}_{indexed}"), table_name=f"workbench_skill_{name}")
        op.drop_index(op.f(f"ix_workbench_skill_{name}_template_id"), table_name=f"workbench_skill_{name}")
        op.drop_table(f"workbench_skill_{name}")
    op.drop_index(op.f("ix_workbench_skill_evidence_template_id"), table_name="workbench_skill_evidence")
    op.drop_table("workbench_skill_evidence")
    table = "workbench_template_pattern"
    op.drop_index(op.f("ix_workbench_template_pattern_status"), table_name=table)
    for column in ("evaluation_summary", "promotion_reason", "output_contract", "required_inputs", "expires_at", "reviewed_at", "platforms", "owner", "version", "status"):
        op.drop_column(table, column)
