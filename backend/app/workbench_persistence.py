from __future__ import annotations

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.models import (
    WorkbenchGeneratedScript,
    WorkbenchHotspotBrief,
    WorkbenchScriptAnalysis,
    WorkbenchSkillEvaluation,
    WorkbenchSkillEvidence,
    WorkbenchSkillReview,
    WorkbenchSourceVideo,
    WorkbenchTemplatePattern,
    WorkbenchTranscript,
    get_datetime_utc,
)
from app.script_workbench import (
    AnalyzeTextResponse,
    GenerateHotspotResponse,
    GeneratedScript,
    GeneratedScriptUpdateRequest,
    GeneratedScriptVersion,
    LinkTaskResponse,
    RiskCheck,
    SkillSourceRecord,
    SkillEvidence,
    SkillEvaluationSummary,
    SkillReviewRecord,
    ScriptSegment,
    ScriptAnalysis,
    SourceVideo,
    TemplatePattern,
    TemplateReviewUpdateRequest,
    Transcript,
    WorkbenchOverview,
    merge_skill_sources,
)


def source_video_to_record(source: SourceVideo) -> WorkbenchSourceVideo:
    return WorkbenchSourceVideo(**source.model_dump())


def transcript_to_record(transcript: Transcript) -> WorkbenchTranscript:
    return WorkbenchTranscript(**transcript.model_dump())


def analysis_to_record(analysis: ScriptAnalysis) -> WorkbenchScriptAnalysis:
    data = analysis.model_dump()
    data["structure"] = [segment.model_dump() for segment in analysis.structure]
    return WorkbenchScriptAnalysis(**data)


def template_to_record(template: TemplatePattern) -> WorkbenchTemplatePattern:
    return WorkbenchTemplatePattern(**template.model_dump(mode="json"))


def save_analysis_response(
    session: Session,
    response: AnalyzeTextResponse,
) -> None:
    """Persist one completed text/subtitle/transcript analysis result."""

    session.merge(source_video_to_record(response.source_video))
    session.merge(transcript_to_record(response.transcript))
    session.merge(analysis_to_record(response.analysis))
    session.commit()


def save_link_task_response(
    session: Session,
    response: LinkTaskResponse,
) -> None:
    session.merge(source_video_to_record(response.source_video))
    session.commit()


def save_hotspot_response(
    session: Session,
    response: GenerateHotspotResponse,
) -> None:
    """Persist a generated hotspot brief and all generated script versions."""

    brief = WorkbenchHotspotBrief(**response.brief.model_dump())
    session.merge(brief)
    for script in response.scripts:
        data = script.model_dump()
        data["hotspot_brief_id"] = brief.id
        data.pop("preset_application", None)
        data["risk_check"] = script.risk_check.model_dump()
        session.merge(WorkbenchGeneratedScript(**data))
    for template in response.matched_templates:
        session.merge(template_to_record(template))
    session.commit()


def save_generated_script(session: Session, script: GeneratedScript) -> None:
    data = script.model_dump()
    data.pop("preset_application", None)
    data["risk_check"] = script.risk_check.model_dump()
    data["version_history"] = [
        version.model_dump(mode="json") for version in script.version_history
    ]
    session.merge(WorkbenchGeneratedScript(**data))
    session.commit()


def update_generated_script_record(
    session: Session,
    script_id: str,
    payload: GeneratedScriptUpdateRequest,
    risk_check: RiskCheck,
) -> GeneratedScript | None:
    record = session.get(WorkbenchGeneratedScript, script_id)
    if record is None:
        return None
    from app.script_workbench import new_id, now_utc

    previous_version = GeneratedScriptVersion(
        id=new_id("version"),
        source_script_id=record.id,
        title=record.title,
        spoken_script=record.spoken_script,
        shot_suggestions=record.shot_suggestions or [],
        subtitle_rhythm=record.subtitle_rhythm or [],
        comment_cta=record.comment_cta,
        production_status=record.production_status or "draft",  # type: ignore[arg-type]
        version_label=record.version_label or "v1",
        editor_note=record.editor_note,
        created_at=record.updated_at or now_utc(),
    )
    record.title = payload.title
    record.spoken_script = payload.spoken_script
    record.shot_suggestions = payload.shot_suggestions
    record.subtitle_rhythm = payload.subtitle_rhythm
    record.comment_cta = payload.comment_cta
    record.risk_check = risk_check.model_dump()
    record.production_status = payload.production_status
    record.version_label = payload.version_label
    record.editor_note = payload.editor_note or None
    record.updated_at = now_utc()
    record.version_history = [
        previous_version.model_dump(mode="json"),
        *(record.version_history or []),
    ][:12]
    session.add(record)
    session.commit()
    session.refresh(record)
    return generated_script_from_record(record)


def copy_generated_script_version_record(
    session: Session,
    script_id: str,
    version_id: str,
) -> GeneratedScript | None:
    record = session.get(WorkbenchGeneratedScript, script_id)
    if record is None:
        return None
    version = next(
        (
            item
            for item in (record.version_history or [])
            if item.get("id") == version_id
        ),
        None,
    )
    if version is None:
        return None
    from app.script_workbench import new_id, now_utc, risk_check

    copied = WorkbenchGeneratedScript(
        id=new_id("script"),
        hotspot_brief_id=record.hotspot_brief_id,
        title=f"{version['title']}｜旧版复制",
        account_type=record.account_type,
        content_angle=record.content_angle,
        duration_seconds=record.duration_seconds,
        spoken_script=version["spoken_script"],
        shot_suggestions=version.get("shot_suggestions") or [],
        subtitle_rhythm=version.get("subtitle_rhythm") or [],
        comment_cta=version["comment_cta"],
        risk_check=risk_check(
            f"{version['title']} {version['spoken_script']} {version['comment_cta']}"
        ).model_dump(),
        template_used=record.template_used,
        production_status="draft",
        version_label=f"{version.get('version_label') or 'v1'}-copy",
        editor_note=f"从 {version.get('version_label') or 'v1'} 历史版本复制。",
        updated_at=now_utc(),
        version_history=[],
    )
    session.add(copied)
    session.commit()
    session.refresh(copied)
    return generated_script_from_record(copied)


def copy_generated_script_record(
    session: Session,
    script_id: str,
) -> GeneratedScript | None:
    record = session.get(WorkbenchGeneratedScript, script_id)
    if record is None:
        return None
    from app.script_workbench import new_id, now_utc, risk_check

    source_version = GeneratedScriptVersion(
        id=new_id("version"),
        source_script_id=record.id,
        title=record.title,
        spoken_script=record.spoken_script,
        shot_suggestions=record.shot_suggestions or [],
        subtitle_rhythm=record.subtitle_rhythm or [],
        comment_cta=record.comment_cta,
        production_status=record.production_status or "draft",  # type: ignore[arg-type]
        version_label=record.version_label or "v1",
        editor_note=record.editor_note,
        created_at=record.updated_at or now_utc(),
    )
    copied = WorkbenchGeneratedScript(
        id=new_id("script"),
        hotspot_brief_id=record.hotspot_brief_id,
        title=f"{record.title}｜复用草稿",
        account_type=record.account_type,
        content_angle=record.content_angle,
        duration_seconds=record.duration_seconds,
        spoken_script=record.spoken_script,
        shot_suggestions=record.shot_suggestions or [],
        subtitle_rhythm=record.subtitle_rhythm or [],
        comment_cta=record.comment_cta,
        risk_check=risk_check(
            f"{record.title} {record.spoken_script} {record.comment_cta}"
        ).model_dump(),
        template_used=record.template_used,
        production_status="draft",
        version_label=f"{record.version_label or 'v1'}-reuse",
        editor_note="从已导出生产单复用为新草稿。"
        if record.production_status == "exported"
        else "从生产单复用为新草稿。",
        updated_at=now_utc(),
        version_history=[source_version.model_dump(mode="json")],
    )
    session.add(copied)
    session.commit()
    session.refresh(copied)
    return generated_script_from_record(copied)


def save_template_pattern(session: Session, template: TemplatePattern) -> None:
    incoming = template_to_record(template)
    record = session.get(WorkbenchTemplatePattern, template.id)
    if record is None:
        session.add(incoming)
    else:
        for field_name in (
            "name",
            "account_type",
            "hotspot_types",
            "solves_problems",
            "match_signals",
            "applicable_scenes",
            "unsuitable_scenes",
            "skeleton",
            "hook_formula",
            "emotion_rhythm",
            "ending_formula",
            "risk_boundary",
            "quality_score",
            "usage_count",
            "disabled_reason",
            "last_review_note",
            "source_analysis_id",
            "source_titles",
            "sources",
            "source_count",
            "pattern_fingerprint",
            "status",
            "version",
            "owner",
            "platforms",
            "reviewed_at",
            "expires_at",
            "required_inputs",
            "output_contract",
            "promotion_reason",
            "evaluation_summary",
        ):
            setattr(record, field_name, getattr(incoming, field_name))
        for field_name in (
            "hotspot_types",
            "solves_problems",
            "match_signals",
            "applicable_scenes",
            "unsuitable_scenes",
            "skeleton",
            "source_titles",
            "sources",
            "platforms",
            "required_inputs",
            "output_contract",
            "evaluation_summary",
        ):
            flag_modified(record, field_name)
        session.add(record)
    session.commit()
    replace_skill_governance_records(session, template)


def replace_skill_governance_records(session: Session, template: TemplatePattern) -> None:
    """Keep evidence and reviewer records queryable while the template retains a compact summary."""
    for row in session.exec(
        select(WorkbenchSkillEvidence).where(WorkbenchSkillEvidence.template_id == template.id)
    ).all():
        session.delete(row)
    for row in session.exec(
        select(WorkbenchSkillReview).where(WorkbenchSkillReview.template_id == template.id)
    ).all():
        session.delete(row)
    for row in session.exec(
        select(WorkbenchSkillEvaluation).where(WorkbenchSkillEvaluation.template_id == template.id)
    ).all():
        session.delete(row)
    for evidence in template.evidence:
        payload = evidence.model_dump(mode="json")
        payload["id"] = payload["id"] or f"evidence_{template.id}_{len(payload['claim'])}"
        session.add(WorkbenchSkillEvidence(template_id=template.id, **payload))
    for review in template.reviews:
        scores = {
            "accuracy": review.accuracy,
            "structure": review.structure,
            "douyin_fit": review.douyin_fit,
            "shootability": review.shootability,
            "distinctiveness": review.distinctiveness,
        }
        session.add(
            WorkbenchSkillReview(
                id=review.id or f"review_{template.id}_{int(review.created_at.timestamp())}",
                template_id=template.id,
                version=template.version,
                reviewer=review.reviewer,
                blind_label=review.blind_label,
                scores=scores,
                approved=review.approved,
                note=review.note,
                created_at=review.created_at,
            )
        )
    summary = template.evaluation_summary
    if summary.evaluated_at:
        session.add(
            WorkbenchSkillEvaluation(
                id=f"eval_{template.id}_{template.version}",
                template_id=template.id,
                version=template.version,
                suite="release",
                model_configuration={},
                result=summary.model_dump(mode="json"),
                passed=summary.passed,
                report_path=summary.report_path,
                created_at=summary.evaluated_at,
            )
        )
    session.commit()


def update_template_review_record(
    session: Session,
    template_id: str,
    payload: TemplateReviewUpdateRequest,
) -> TemplatePattern | None:
    record = session.get(WorkbenchTemplatePattern, template_id)
    if record is None:
        return None
    record.quality_score = payload.quality_score
    record.applicable_scenes = payload.applicable_scenes
    record.unsuitable_scenes = payload.unsuitable_scenes
    record.disabled_reason = payload.disabled_reason or None
    record.last_review_note = payload.last_review_note or None
    session.add(record)
    session.commit()
    session.refresh(record)
    return template_from_record(record)


def list_recent_templates(
    session: Session, limit: int = 20
) -> list[WorkbenchTemplatePattern]:
    statement = (
        select(WorkbenchTemplatePattern)
        .order_by(WorkbenchTemplatePattern.created_at.desc())  # type: ignore[attr-defined]
        .limit(limit)
    )
    return list(session.exec(statement).all())


def list_recent_generated_scripts(
    session: Session,
    limit: int = 20,
) -> list[WorkbenchGeneratedScript]:
    statement = (
        select(WorkbenchGeneratedScript)
        .order_by(WorkbenchGeneratedScript.created_at.desc())  # type: ignore[attr-defined]
        .limit(limit)
    )
    return list(session.exec(statement).all())


def template_from_record(
    record: WorkbenchTemplatePattern,
    sources: list[SkillSourceRecord] | None = None,
) -> TemplatePattern:
    hydrated_sources = (
        sources
        if sources is not None
        else [SkillSourceRecord(**item) for item in (record.sources or [])]
    )
    created_at = record.created_at or max(
        (source.recognized_at for source in hydrated_sources if source.recognized_at),
        default=None,
    )
    return TemplatePattern(
        id=record.id,
        name=record.name,
        account_type=record.account_type,
        hotspot_types=record.hotspot_types or [],
        solves_problems=record.solves_problems or [],
        match_signals=record.match_signals or [],
        applicable_scenes=record.applicable_scenes or [],
        unsuitable_scenes=record.unsuitable_scenes or [],
        skeleton=record.skeleton or [],
        hook_formula=record.hook_formula,
        emotion_rhythm=record.emotion_rhythm,
        ending_formula=record.ending_formula,
        risk_boundary=record.risk_boundary,
        quality_score=record.quality_score or 80,
        usage_count=record.usage_count,
        disabled_reason=record.disabled_reason,
        last_review_note=record.last_review_note,
        source_analysis_id=record.source_analysis_id,
        source_titles=record.source_titles or [],
        sources=hydrated_sources,
        source_count=(
            len(hydrated_sources)
            if hydrated_sources
            else len(record.source_titles or [])
        ),
        pattern_fingerprint=record.pattern_fingerprint or "",
        status=record.status or "candidate",
        version=record.version or 1,
        owner=record.owner or "内容主审",
        platforms=record.platforms or ["douyin"],
        reviewed_at=record.reviewed_at,
        expires_at=record.expires_at,
        required_inputs=record.required_inputs or [],
        output_contract=record.output_contract or [],
        promotion_reason=record.promotion_reason,
        evaluation_summary=SkillEvaluationSummary(**(record.evaluation_summary or {})),
        created_at=created_at or get_datetime_utc(),
    )


def analysis_from_record(record: WorkbenchScriptAnalysis) -> ScriptAnalysis:
    return ScriptAnalysis(
        id=record.id,
        source_video_id=record.source_video_id,
        hook=record.hook,
        conflict=record.conflict,
        structure=[ScriptSegment(**segment) for segment in record.structure],
        emotion_curve=record.emotion_curve,
        reversal=record.reversal,
        ending_cta=record.ending_cta,
        account_type=record.account_type,
        reusable_template=record.reusable_template,
        template_suggestions=record.template_suggestions,
        content_angle=record.content_angle,
    )


def generated_script_from_record(record: WorkbenchGeneratedScript) -> GeneratedScript:
    return GeneratedScript(
        id=record.id,
        title=record.title,
        account_type=record.account_type,
        content_angle=record.content_angle,
        duration_seconds=record.duration_seconds,
        spoken_script=record.spoken_script,
        shot_suggestions=record.shot_suggestions,
        subtitle_rhythm=record.subtitle_rhythm,
        comment_cta=record.comment_cta,
        risk_check=RiskCheck(**record.risk_check),
        template_used=record.template_used,
        preset_application=[],
        production_status=record.production_status or "draft",  # type: ignore[arg-type]
        version_label=record.version_label or "v1",
        editor_note=record.editor_note,
        updated_at=record.updated_at,
        version_history=[
            GeneratedScriptVersion(**version)
            for version in (record.version_history or [])
        ],
    )


def hydrate_skill_sources(
    session: Session,
    record: WorkbenchTemplatePattern,
) -> list[SkillSourceRecord]:
    sources = [SkillSourceRecord(**item) for item in (record.sources or [])]
    known_video_ids = {item.source_video_id for item in sources}
    known_urls = {
        item.url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        for item in sources
        if item.url
    }

    candidate_videos: list[tuple[WorkbenchSourceVideo, str | None]] = []
    if record.source_analysis_id:
        analysis = session.get(WorkbenchScriptAnalysis, record.source_analysis_id)
        if analysis is not None:
            source = session.get(WorkbenchSourceVideo, analysis.source_video_id)
            if source is not None:
                candidate_videos.append((source, analysis.id))

    for title in record.source_titles or []:
        source = session.exec(
            select(WorkbenchSourceVideo)
            .where(WorkbenchSourceVideo.title == title)
            .order_by(WorkbenchSourceVideo.created_at.desc())  # type: ignore[attr-defined]
        ).first()
        if source is not None:
            candidate_videos.append((source, None))

    for source, analysis_id in candidate_videos:
        normalized_url = (
            source.url.split("?", 1)[0].split("#", 1)[0].rstrip("/")
            if source.url
            else ""
        )
        if source.id in known_video_ids or (
            normalized_url and normalized_url in known_urls
        ):
            continue
        transcript = session.exec(
            select(WorkbenchTranscript)
            .where(WorkbenchTranscript.source_video_id == source.id)
            .order_by(WorkbenchTranscript.created_at.desc())  # type: ignore[attr-defined]
        ).first()
        sources.append(
            SkillSourceRecord(
                source_video_id=source.id,
                source_analysis_id=analysis_id,
                title=source.title,
                author=source.author,
                url=source.url,
                transcript=transcript.content_text if transcript is not None else "",
                recognized_at=(
                    transcript.created_at
                    if transcript is not None
                    else source.created_at
                ),
            )
        )
        known_video_ids.add(source.id)
        if normalized_url:
            known_urls.add(normalized_url)
    return merge_skill_sources(sources)


def hydrate_and_persist_skill_sources(
    session: Session,
    record: WorkbenchTemplatePattern,
) -> list[SkillSourceRecord]:
    sources = hydrate_skill_sources(session, record)
    serialized = [source.model_dump(mode="json") for source in sources]
    source_titles = [source.title for source in sources if source.title] or (
        record.source_titles or []
    )
    source_count = max(len(sources), len(source_titles), 0)
    source_created_at = max(
        (source.recognized_at for source in sources if source.recognized_at),
        default=None,
    )
    should_fill_created_at = record.created_at is None and source_created_at is not None
    if should_fill_created_at:
        record.created_at = source_created_at
    if (
        serialized != (record.sources or [])
        or source_titles != (record.source_titles or [])
        or source_count != (record.source_count or 0)
        or should_fill_created_at
    ):
        record.sources = serialized
        record.source_titles = source_titles
        record.source_count = source_count
        flag_modified(record, "sources")
        flag_modified(record, "source_titles")
        session.add(record)
        session.commit()
        session.refresh(record)
    return sources


def template_with_governance(
    session: Session, record: WorkbenchTemplatePattern, sources: list[SkillSourceRecord]
) -> TemplatePattern:
    template = template_from_record(record, sources)
    evidence = [
        SkillEvidence(**row.model_dump())
        for row in session.exec(
            select(WorkbenchSkillEvidence).where(WorkbenchSkillEvidence.template_id == record.id)
        ).all()
    ]
    reviews: list[SkillReviewRecord] = []
    for row in session.exec(
        select(WorkbenchSkillReview)
        .where(WorkbenchSkillReview.template_id == record.id)
        .order_by(WorkbenchSkillReview.created_at.desc())  # type: ignore[attr-defined]
    ).all():
        scores = row.scores or {}
        try:
            reviews.append(
                SkillReviewRecord(
                    id=row.id,
                    reviewer=row.reviewer,
                    blind_label=row.blind_label,
                    accuracy=int(scores.get("accuracy", 1)),
                    structure=int(scores.get("structure", 1)),
                    douyin_fit=int(scores.get("douyin_fit", 1)),
                    shootability=int(scores.get("shootability", 1)),
                    distinctiveness=int(scores.get("distinctiveness", 1)),
                    approved=row.approved,
                    note=row.note,
                    created_at=row.created_at or get_datetime_utc(),
                )
            )
        except Exception:
            continue
    return template.model_copy(update={"evidence": evidence, "reviews": reviews})


def overview_from_database(session: Session) -> WorkbenchOverview:
    templates = [
        template_with_governance(session, record, hydrate_and_persist_skill_sources(session, record))
        for record in session.exec(
            select(WorkbenchTemplatePattern)
            .order_by(WorkbenchTemplatePattern.created_at.desc())  # type: ignore[attr-defined]
            .limit(20)
        ).all()
    ]
    recent_analyses = [
        analysis_from_record(record)
        for record in session.exec(
            select(WorkbenchScriptAnalysis)
            .order_by(WorkbenchScriptAnalysis.created_at.desc())  # type: ignore[attr-defined]
            .limit(8)
        ).all()
    ]
    generated_scripts = [
        generated_script_from_record(record)
        for record in session.exec(
            select(WorkbenchGeneratedScript)
            .order_by(WorkbenchGeneratedScript.created_at.desc())  # type: ignore[attr-defined]
            .limit(8)
        ).all()
    ]
    source_count = len(session.exec(select(WorkbenchSourceVideo.id)).all())
    failed_count = len(
        session.exec(
            select(WorkbenchSourceVideo.id).where(
                WorkbenchSourceVideo.status == "failed"
            )
        ).all()
    )
    processing_count = len(
        session.exec(
            select(WorkbenchSourceVideo.id).where(
                WorkbenchSourceVideo.status.in_(
                    ["pending", "processing", "needs_upload"]
                )  # type: ignore[attr-defined]
            )
        ).all()
    )
    return WorkbenchOverview(
        tasks={
            "processing": processing_count,
            "queued": 0,
            "completed": source_count,
            "failed": failed_count,
        },
        templates=templates,
        recent_analyses=recent_analyses,
        generated_scripts=generated_scripts,
    )
