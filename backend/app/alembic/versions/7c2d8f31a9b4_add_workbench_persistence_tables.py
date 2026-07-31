"""Add workbench persistence tables

Revision ID: 7c2d8f31a9b4
Revises: fe56fa70289e
Create Date: 2026-07-25 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = "7c2d8f31a9b4"
down_revision = "fe56fa70289e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workbench_source_video",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("input_type", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("url", sqlmodel.sql.sqltypes.AutoString(length=1024), nullable=True),
        sa.Column("author", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column("publish_time", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("material_path", sqlmodel.sql.sqltypes.AutoString(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workbench_source_video_input_type"), "workbench_source_video", ["input_type"], unique=False)
    op.create_index(op.f("ix_workbench_source_video_status"), "workbench_source_video", ["status"], unique=False)
    op.create_index(op.f("ix_workbench_source_video_title"), "workbench_source_video", ["title"], unique=False)

    op.create_table(
        "workbench_transcript",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("source_video_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("asr_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ocr_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("content_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("timestamps", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_video_id"], ["workbench_source_video.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workbench_transcript_source"), "workbench_transcript", ["source"], unique=False)
    op.create_index(op.f("ix_workbench_transcript_source_video_id"), "workbench_transcript", ["source_video_id"], unique=False)

    op.create_table(
        "workbench_script_analysis",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("source_video_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("hook", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("conflict", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("structure", sa.JSON(), nullable=True),
        sa.Column("emotion_curve", sa.JSON(), nullable=True),
        sa.Column("reversal", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ending_cta", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("account_type", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("reusable_template", sqlmodel.sql.sqltypes.AutoString(length=160), nullable=False),
        sa.Column("template_suggestions", sa.JSON(), nullable=True),
        sa.Column("content_angle", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_video_id"], ["workbench_source_video.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workbench_script_analysis_account_type"), "workbench_script_analysis", ["account_type"], unique=False)
    op.create_index(op.f("ix_workbench_script_analysis_source_video_id"), "workbench_script_analysis", ["source_video_id"], unique=False)

    op.create_table(
        "workbench_template_pattern",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=160), nullable=False),
        sa.Column("account_type", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("hotspot_types", sa.JSON(), nullable=True),
        sa.Column("skeleton", sa.JSON(), nullable=True),
        sa.Column("hook_formula", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("emotion_rhythm", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ending_formula", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("risk_boundary", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False),
        sa.Column("source_analysis_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_analysis_id"], ["workbench_script_analysis.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workbench_template_pattern_account_type"), "workbench_template_pattern", ["account_type"], unique=False)
    op.create_index(op.f("ix_workbench_template_pattern_name"), "workbench_template_pattern", ["name"], unique=False)
    op.create_index(op.f("ix_workbench_template_pattern_source_analysis_id"), "workbench_template_pattern", ["source_analysis_id"], unique=False)

    op.create_table(
        "workbench_hotspot_brief",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("event_summary", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("controversy", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("audience_emotion", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("angles", sa.JSON(), nullable=True),
        sa.Column("no_go_zones", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "workbench_generated_script",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(length=64), nullable=False),
        sa.Column("hotspot_brief_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("title", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column("account_type", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("content_angle", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("spoken_script", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("shot_suggestions", sa.JSON(), nullable=True),
        sa.Column("subtitle_rhythm", sa.JSON(), nullable=True),
        sa.Column("comment_cta", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("risk_check", sa.JSON(), nullable=True),
        sa.Column("template_used", sqlmodel.sql.sqltypes.AutoString(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["hotspot_brief_id"], ["workbench_hotspot_brief.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workbench_generated_script_account_type"), "workbench_generated_script", ["account_type"], unique=False)
    op.create_index(op.f("ix_workbench_generated_script_content_angle"), "workbench_generated_script", ["content_angle"], unique=False)
    op.create_index(op.f("ix_workbench_generated_script_hotspot_brief_id"), "workbench_generated_script", ["hotspot_brief_id"], unique=False)
    op.create_index(op.f("ix_workbench_generated_script_template_used"), "workbench_generated_script", ["template_used"], unique=False)
    op.create_index(op.f("ix_workbench_generated_script_title"), "workbench_generated_script", ["title"], unique=False)

    op.create_table(
        "workbench_account_asset",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=160), nullable=False),
        sa.Column("account_type", sqlmodel.sql.sqltypes.AutoString(length=80), nullable=False),
        sa.Column("platform", sqlmodel.sql.sqltypes.AutoString(length=32), nullable=False),
        sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workbench_account_asset_account_type"), "workbench_account_asset", ["account_type"], unique=False)
    op.create_index(op.f("ix_workbench_account_asset_name"), "workbench_account_asset", ["name"], unique=False)
    op.create_index(op.f("ix_workbench_account_asset_platform"), "workbench_account_asset", ["platform"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_workbench_account_asset_platform"), table_name="workbench_account_asset")
    op.drop_index(op.f("ix_workbench_account_asset_name"), table_name="workbench_account_asset")
    op.drop_index(op.f("ix_workbench_account_asset_account_type"), table_name="workbench_account_asset")
    op.drop_table("workbench_account_asset")
    op.drop_index(op.f("ix_workbench_generated_script_title"), table_name="workbench_generated_script")
    op.drop_index(op.f("ix_workbench_generated_script_template_used"), table_name="workbench_generated_script")
    op.drop_index(op.f("ix_workbench_generated_script_hotspot_brief_id"), table_name="workbench_generated_script")
    op.drop_index(op.f("ix_workbench_generated_script_content_angle"), table_name="workbench_generated_script")
    op.drop_index(op.f("ix_workbench_generated_script_account_type"), table_name="workbench_generated_script")
    op.drop_table("workbench_generated_script")
    op.drop_table("workbench_hotspot_brief")
    op.drop_index(op.f("ix_workbench_template_pattern_source_analysis_id"), table_name="workbench_template_pattern")
    op.drop_index(op.f("ix_workbench_template_pattern_name"), table_name="workbench_template_pattern")
    op.drop_index(op.f("ix_workbench_template_pattern_account_type"), table_name="workbench_template_pattern")
    op.drop_table("workbench_template_pattern")
    op.drop_index(op.f("ix_workbench_script_analysis_source_video_id"), table_name="workbench_script_analysis")
    op.drop_index(op.f("ix_workbench_script_analysis_account_type"), table_name="workbench_script_analysis")
    op.drop_table("workbench_script_analysis")
    op.drop_index(op.f("ix_workbench_transcript_source_video_id"), table_name="workbench_transcript")
    op.drop_index(op.f("ix_workbench_transcript_source"), table_name="workbench_transcript")
    op.drop_table("workbench_transcript")
    op.drop_index(op.f("ix_workbench_source_video_title"), table_name="workbench_source_video")
    op.drop_index(op.f("ix_workbench_source_video_status"), table_name="workbench_source_video")
    op.drop_index(op.f("ix_workbench_source_video_input_type"), table_name="workbench_source_video")
    op.drop_table("workbench_source_video")
