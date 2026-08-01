import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import EmailStr
from sqlalchemy import Column, DateTime, JSON
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(UTC)


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(SQLModel):
    email: EmailStr | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    is_superuser: bool | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    items: list[Item] = Relationship(back_populates="owner", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(SQLModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class WorkbenchSourceVideo(SQLModel, table=True):
    __tablename__ = "workbench_source_video"

    id: str = Field(primary_key=True, max_length=64)
    input_type: str = Field(index=True, max_length=32)
    title: str = Field(index=True, max_length=255)
    url: str | None = Field(default=None, max_length=1024)
    author: str | None = Field(default=None, max_length=255)
    publish_time: str | None = Field(default=None, max_length=64)
    status: str = Field(index=True, max_length=32)
    material_path: str | None = Field(default=None, max_length=1024)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class WorkbenchTranscript(SQLModel, table=True):
    __tablename__ = "workbench_transcript"

    id: str = Field(primary_key=True, max_length=64)
    source_video_id: str = Field(foreign_key="workbench_source_video.id", index=True)
    asr_text: str = ""
    ocr_text: str = ""
    content_text: str
    timestamps: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    confidence: float = 0.0
    source: str = Field(index=True, max_length=32)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class WorkbenchScriptAnalysis(SQLModel, table=True):
    __tablename__ = "workbench_script_analysis"

    id: str = Field(primary_key=True, max_length=64)
    source_video_id: str = Field(foreign_key="workbench_source_video.id", index=True)
    hook: str
    conflict: str
    structure: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    emotion_curve: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    reversal: str
    ending_cta: str
    account_type: str = Field(index=True, max_length=80)
    reusable_template: str = Field(max_length=160)
    template_suggestions: list[str] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    content_angle: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class WorkbenchTemplatePattern(SQLModel, table=True):
    __tablename__ = "workbench_template_pattern"

    id: str = Field(primary_key=True, max_length=64)
    name: str = Field(index=True, max_length=160)
    account_type: str = Field(index=True, max_length=80)
    hotspot_types: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    solves_problems: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    match_signals: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    applicable_scenes: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    unsuitable_scenes: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    skeleton: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    hook_formula: str
    emotion_rhythm: str
    ending_formula: str
    risk_boundary: str
    quality_score: int = Field(default=80, index=True)
    usage_count: int = 0
    disabled_reason: str | None = None
    last_review_note: str | None = None
    source_analysis_id: str | None = Field(
        default=None, foreign_key="workbench_script_analysis.id", index=True
    )
    source_titles: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    sources: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    source_count: int = Field(default=0)
    pattern_fingerprint: str = Field(default="", index=True, max_length=40)
    status: str = Field(default="candidate", index=True, max_length=20)
    version: int = Field(default=1)
    owner: str = Field(default="内容主审", max_length=120)
    platforms: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    reviewed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    expires_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    required_inputs: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    output_contract: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    promotion_reason: str | None = None
    evaluation_summary: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class WorkbenchSkillEvidence(SQLModel, table=True):
    __tablename__ = "workbench_skill_evidence"

    id: str = Field(primary_key=True, max_length=64)
    template_id: str = Field(foreign_key="workbench_template_pattern.id", index=True)
    claim: str
    source_title: str = Field(max_length=200)
    source_url: str = Field(max_length=500)
    source_type: str = Field(default="user_provided", max_length=80)
    evidence_tier: str = Field(default="A", max_length=4)
    quote: str = ""
    scope: str = Field(default="structure", max_length=20)
    checked_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))  # type: ignore


class WorkbenchSkillEvaluation(SQLModel, table=True):
    __tablename__ = "workbench_skill_evaluation"

    id: str = Field(primary_key=True, max_length=64)
    template_id: str = Field(foreign_key="workbench_template_pattern.id", index=True)
    version: int
    suite: str = Field(max_length=80)
    model_configuration: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column("model_config", JSON),
    )
    result: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    passed: bool = Field(default=False, index=True)
    report_path: str | None = Field(default=None, max_length=500)
    created_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))  # type: ignore


class WorkbenchSkillReview(SQLModel, table=True):
    __tablename__ = "workbench_skill_review"

    id: str = Field(primary_key=True, max_length=64)
    template_id: str = Field(foreign_key="workbench_template_pattern.id", index=True)
    version: int
    reviewer: str = Field(default="内容主审", max_length=120)
    blind_label: str = Field(default="", max_length=32)
    scores: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    approved: bool = Field(default=False, index=True)
    note: str = ""
    created_at: datetime | None = Field(default_factory=get_datetime_utc, sa_type=DateTime(timezone=True))  # type: ignore


class WorkbenchHotspotBrief(SQLModel, table=True):
    __tablename__ = "workbench_hotspot_brief"

    id: str = Field(primary_key=True, max_length=64)
    event_summary: str
    controversy: str
    audience_emotion: str
    angles: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    no_go_zones: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class WorkbenchGeneratedScript(SQLModel, table=True):
    __tablename__ = "workbench_generated_script"

    id: str = Field(primary_key=True, max_length=64)
    hotspot_brief_id: str | None = Field(
        default=None, foreign_key="workbench_hotspot_brief.id", index=True
    )
    title: str = Field(index=True, max_length=255)
    account_type: str = Field(index=True, max_length=80)
    content_angle: str = Field(index=True, max_length=80)
    duration_seconds: int
    spoken_script: str
    shot_suggestions: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    subtitle_rhythm: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    comment_cta: str
    risk_check: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    template_used: str = Field(index=True, max_length=160)
    production_status: str = Field(default="draft", index=True, max_length=32)
    version_label: str = Field(default="v1", max_length=40)
    editor_note: str | None = None
    updated_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    version_history: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON)
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )


class WorkbenchAccountAsset(SQLModel, table=True):
    __tablename__ = "workbench_account_asset"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True, max_length=160)
    account_type: str = Field(index=True, max_length=80)
    platform: str = Field(default="douyin", index=True, max_length=32)
    notes: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
