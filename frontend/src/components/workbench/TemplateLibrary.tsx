import {
  BrainCircuit,
  ExternalLink,
  FileText,
  Layers3,
  RotateCcw,
  Save,
  Search,
  Settings2,
  SlidersHorizontal,
  Video,
} from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { fetchSkillPromotionReadiness } from "@/api/workbench"
import type {
  SkillApprovalAndPublishResponse,
  SkillGovernancePayload,
  SkillPromotionReadiness,
  TemplatePattern,
  TemplateReviewPayload,
} from "@/types/workbench"
import { Badge, Card, EmptyState, SectionHeader } from "./ui"

type ReviewDraft = {
  quality_score: number
  applicable_scenes_text: string
  unsuitable_scenes_text: string
  disabled_reason: string
  last_review_note: string
}

type DetailTab = "overview" | "structure" | "sources" | "evaluation" | "manage"

function listToText(items?: string[]) {
  return (items || []).join("\n")
}

function textToList(value: string) {
  const seen = new Set<string>()
  return value
    .split(/\n+/)
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false
      seen.add(item)
      return true
    })
}

function draftFromTemplate(template: TemplatePattern): ReviewDraft {
  return {
    quality_score: template.quality_score || 80,
    applicable_scenes_text: listToText(template.applicable_scenes),
    unsuitable_scenes_text: listToText(template.unsuitable_scenes),
    disabled_reason: template.disabled_reason || "",
    last_review_note: template.last_review_note || "",
  }
}

function skillProblem(template: TemplatePattern) {
  if (template.solves_problems?.length)
    return template.solves_problems.slice(0, 2).join("；")
  const skeleton = template.skeleton.join("")
  if (/[开头爆点钩子反问]/.test(skeleton))
    return "解决开头不抓人、切入太平的问题。"
  if (/[时间线信息分步背景]/.test(skeleton))
    return "解决信息散、推进顺序不清的问题。"
  if (/[情绪对照共鸣痛点]/.test(skeleton))
    return "解决情绪起伏弱、用户代入不足的问题。"
  return "解决结构松散、结尾缺互动的问题。"
}

function skillMatchSignals(template: TemplatePattern) {
  if (template.match_signals?.length) return template.match_signals.slice(0, 8)
  return [
    template.name,
    ...template.hotspot_types,
    ...(template.applicable_scenes || []),
  ]
    .filter(Boolean)
    .slice(0, 6)
}

function formatRecognizedTime(value?: string | null) {
  if (!value) return "识别时间未记录"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date)
}

function formatSkillCreatedDate(value?: string | null) {
  if (!value) return "未记录"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date)
}

function evaluationStatus(template: TemplatePattern) {
  const summary = template.evaluation_summary
  if (!summary?.evaluated_at) return "尚未运行"
  return summary.passed ? "评测通过" : "评测未达标"
}

function skillAddedTimestamp(template: TemplatePattern) {
  const createdAt = template.created_at
    ? new Date(template.created_at).getTime()
    : 0
  if (createdAt > 0) return createdAt
  return Math.max(
    0,
    ...(template.sources || []).map((source) => {
      const recognizedAt = source.recognized_at
        ? new Date(source.recognized_at).getTime()
        : 0
      return Number.isNaN(recognizedAt) ? 0 : recognizedAt
    }),
  )
}

function skillAddedDateValue(template: TemplatePattern) {
  if (template.created_at) return template.created_at
  const latestSource = (template.sources || [])
    .filter((source) => source.recognized_at)
    .sort(
      (a, b) =>
        new Date(b.recognized_at || "").getTime() -
        new Date(a.recognized_at || "").getTime(),
    )[0]
  return latestSource?.recognized_at || null
}

function sourceEvidenceCount(template: TemplatePattern) {
  return Math.max(
    template.sources?.length || 0,
    template.source_titles?.length || 0,
  )
}

function sourceEvidenceLabel(template: TemplatePattern) {
  const count = sourceEvidenceCount(template)
  return count > 0 ? `${count} 个来源` : "缺少证据链"
}

export function TemplateLibrary({
  templates,
  selectedTemplateId,
  onReviewTemplate,
  onGovernSkill,
  onApproveAndPublish,
  onContinueEvidence,
}: {
  templates: TemplatePattern[]
  selectedTemplateId: string | null
  onReviewTemplate: (
    templateId: string,
    payload: TemplateReviewPayload,
  ) => Promise<TemplatePattern>
  onGovernSkill: (
    templateId: string,
    payload: SkillGovernancePayload,
  ) => Promise<TemplatePattern>
  onApproveAndPublish: (
    templateId: string,
    payload: SkillGovernancePayload,
  ) => Promise<SkillApprovalAndPublishResponse>
  onContinueEvidence: (template: TemplatePattern) => void
}) {
  const [query, setQuery] = useState("")
  const [structureFilter, setStructureFilter] = useState("全部结构")
  const [focusedTemplateId, setFocusedTemplateId] = useState<string | null>(
    selectedTemplateId,
  )
  const [isEditing, setIsEditing] = useState(false)
  const [reviewDraft, setReviewDraft] = useState<ReviewDraft | null>(null)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [reviewSaving, setReviewSaving] = useState(false)
  const [detailTab, setDetailTab] = useState<DetailTab>("overview")
  const [governanceSaving, setGovernanceSaving] = useState(false)
  const [promotionReadiness, setPromotionReadiness] =
    useState<SkillPromotionReadiness | null>(null)
  const allTemplates = useMemo(() => {
    return templates
      .filter(
        (item, index, list) =>
          list.findIndex((candidate) => candidate.id === item.id) === index,
      )
      .sort(
        (a, b) =>
          skillAddedTimestamp(b) - skillAddedTimestamp(a) ||
          (b.quality_score || 80) - (a.quality_score || 80) ||
          b.usage_count - a.usage_count,
      )
  }, [templates])
  const structureTypes = [
    "全部结构",
    ...Array.from(
      new Set(allTemplates.flatMap((template) => template.hotspot_types)),
    ),
  ]
  const averageScore = allTemplates.length
    ? Math.round(
        allTemplates.reduce(
          (sum, template) => sum + (template.quality_score || 80),
          0,
        ) / allTemplates.length,
      )
    : 0
  const visible = allTemplates.filter((template) => {
    const searchable = `${template.name}${template.account_type}${template.hotspot_types.join("")}${template.solves_problems?.join("") || ""}${template.match_signals?.join("") || ""}${template.applicable_scenes?.join("") || ""}${template.hook_formula}`
    const textMatched = searchable.includes(query)
    const structureMatched =
      structureFilter === "全部结构" ||
      template.hotspot_types.includes(structureFilter)
    return textMatched && structureMatched
  })
  const focusedTemplate =
    allTemplates.find(
      (template) => template.id === (focusedTemplateId || selectedTemplateId),
    ) || visible[0]
  const scoreTone = (score = 80): "success" | "accent" | "warning" =>
    score >= 88 ? "success" : score >= 72 ? "accent" : "warning"
  const sourceRemaining = promotionReadiness
    ? Math.max(
        0,
        promotionReadiness.required_source_count - promotionReadiness.source_count,
      )
    : 0
  const needsSourcePreparation =
    promotionReadiness !== null &&
    (sourceRemaining > 0 || !promotionReadiness.has_structure_evidence)
  const statusLabel = (status?: TemplatePattern["status"]) =>
    status === "active"
      ? "正式"
      : status === "paused"
        ? "暂停"
        : status === "retired"
          ? "退役"
          : "候选"
  const updateStatus = async (
    status: NonNullable<TemplatePattern["status"]>,
  ) => {
    if (!focusedTemplate) return
    if (
      status === "retired" &&
      !window.confirm(
        "退役后将永久退出路由和公开发布，但会保留全部历史记录。确认退役？",
      )
    ) {
      return
    }
    setGovernanceSaving(true)
    setReviewError(null)
    try {
      await onGovernSkill(focusedTemplate.id, {
        status,
        owner: focusedTemplate.owner || "内容主审",
        platforms: focusedTemplate.platforms || ["douyin"],
        required_inputs: focusedTemplate.required_inputs || [],
        output_contract: focusedTemplate.output_contract || [],
        promotion_reason: focusedTemplate.promotion_reason || null,
        expires_at: focusedTemplate.expires_at || null,
        evidence: focusedTemplate.evidence || [],
        evaluation_summary: focusedTemplate.evaluation_summary || {
          passed: false,
        },
        release_report_path: "skill-release-report.json",
        review: null,
      })
    } catch (event) {
      setReviewError(
        event instanceof Error ? event.message : "Skill 状态更新失败",
      )
    } finally {
      setGovernanceSaving(false)
    }
  }
  useEffect(() => {
    if (!focusedTemplate) return
    setReviewDraft(draftFromTemplate(focusedTemplate))
    setReviewError(null)
    setIsEditing(false)
    setDetailTab("overview")
  }, [focusedTemplate])

  useEffect(() => {
    if (!focusedTemplate) return
    let cancelled = false
    setPromotionReadiness(null)
    void fetchSkillPromotionReadiness(focusedTemplate.id)
      .then((readiness) => {
        if (!cancelled) setPromotionReadiness(readiness)
      })
      .catch((event) => {
        if (!cancelled) {
          setReviewError(
            event instanceof Error ? event.message : "无法读取 Skill 发布资格。",
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [focusedTemplate?.id])

  useEffect(() => {
    if (selectedTemplateId) setFocusedTemplateId(selectedTemplateId)
  }, [selectedTemplateId])

  const approveAndPublish = async () => {
    if (!focusedTemplate) return
    setGovernanceSaving(true)
    setReviewError(null)
    try {
      await onApproveAndPublish(focusedTemplate.id, {
        status: "active",
        owner: focusedTemplate.owner || "内容主审",
        platforms: focusedTemplate.platforms || ["douyin"],
        required_inputs: focusedTemplate.required_inputs || [],
        output_contract: focusedTemplate.output_contract || [],
        promotion_reason: focusedTemplate.promotion_reason || null,
        expires_at: focusedTemplate.expires_at || null,
        evidence: focusedTemplate.evidence || [],
        evaluation_summary: focusedTemplate.evaluation_summary || {
          passed: false,
        },
        release_report_path: "skill-release-report.json",
        review: {
          reviewer: focusedTemplate.owner || "内容主审",
          blind_label: "primary",
          accuracy: 4,
          structure: 4,
          douyin_fit: 4,
          shootability: 4,
          distinctiveness: 4,
          approved: true,
          note: "内容主审通过一键审核与 GitHub 同步确认。",
        },
      })
    } catch (event) {
      setReviewError(
        event instanceof Error ? event.message : "Skill 审核与 GitHub 同步失败",
      )
    } finally {
      setGovernanceSaving(false)
    }
  }

  const saveReview = async () => {
    if (!focusedTemplate || !reviewDraft) return
    setReviewError(null)
    if (reviewDraft.quality_score < 0 || reviewDraft.quality_score > 100) {
      setReviewError("质量分必须在 0 到 100 之间。")
      return
    }
    const payload: TemplateReviewPayload = {
      quality_score: reviewDraft.quality_score,
      applicable_scenes: textToList(reviewDraft.applicable_scenes_text),
      unsuitable_scenes: textToList(reviewDraft.unsuitable_scenes_text),
      disabled_reason: reviewDraft.disabled_reason.trim() || null,
      last_review_note: reviewDraft.last_review_note.trim() || null,
    }
    setReviewSaving(true)
    try {
      const updated = await onReviewTemplate(focusedTemplate.id, payload)
      setFocusedTemplateId(updated.id)
      setReviewDraft(draftFromTemplate(updated))
      setIsEditing(false)
    } catch (event) {
      setReviewError(
        event instanceof Error ? event.message : "预设复盘保存失败",
      )
    } finally {
      setReviewSaving(false)
    }
  }

  return (
    <div className="page-grid page-grid-two template-layout">
      <Card>
        <SectionHeader
          title="写作 Skill 库"
          description="这里只管理从好视频和人工规则沉淀出的可复用写作能力；重点看结构适用条件，不按题材硬套。"
        />
        <div className="asset-kpi-row">
          <div>
            <span>Skill 总数</span>
            <strong>{allTemplates.length}</strong>
          </div>
          <div>
            <span>当前筛选</span>
            <strong>{visible.length}</strong>
          </div>
          <div>
            <span>来源样本</span>
            <strong>
              {allTemplates.reduce(
                (sum, template) => sum + sourceEvidenceCount(template),
                0,
              )}
            </strong>
          </div>
          <div>
            <span>平均质量分</span>
            <strong>{averageScore}</strong>
          </div>
        </div>
        <div className="filter-bar filter-bar-extended">
          <Search size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索风格、稿件问题、匹配信号或适用场景"
          />
          <select
            aria-label="按结构能力筛选"
            value={structureFilter}
            onChange={(event) => setStructureFilter(event.target.value)}
          >
            {structureTypes.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
          <Badge tone="accent">{visible.length} 个 Skill</Badge>
        </div>
        {visible.length ? (
          <ul className="skill-library-list" aria-label="写作 Skill 列表">
            {visible.map((template) => (
              <li
                key={template.id}
                className={`skill-library-row ${template.id === focusedTemplate?.id ? "is-focused" : ""}`}
              >
                <button
                  type="button"
                  className="skill-row-preview-button"
                  aria-label={`预览 Skill：${template.name}`}
                  aria-pressed={template.id === focusedTemplate?.id}
                  data-skill-id={template.id}
                  onClick={() => setFocusedTemplateId(template.id)}
                >
                  <div className="skill-row-main">
                    <div className="skill-row-title">
                      <span className="table-link-button">{template.name}</span>
                      <Badge tone={scoreTone(template.quality_score)}>
                        {template.quality_score || 80} 分
                      </Badge>
                      <Badge
                        tone={
                          template.status === "active"
                            ? "success"
                            : template.status === "candidate"
                              ? "accent"
                              : "warning"
                        }
                      >
                        {statusLabel(template.status)}
                      </Badge>
                    </div>
                    <strong className="skill-row-problem">
                      {skillProblem(template)}
                    </strong>
                    <p>
                      {template.applicable_scenes?.slice(0, 2).join("；") ||
                        "等待补充结构适用条件"}
                    </p>
                    <div className="chip-row skill-row-signals">
                      {skillMatchSignals(template)
                        .slice(0, 4)
                        .map((item) => (
                          <Badge key={item}>{item}</Badge>
                        ))}
                    </div>
                  </div>
                </button>
                <div className="skill-row-meta">
                  <span>{sourceEvidenceLabel(template)}</span>
                  <span>
                    添加日期{" "}
                    {formatSkillCreatedDate(skillAddedDateValue(template))}
                  </span>
                  <span>{statusLabel(template.status)}</span>
                  {template.status === "active" ? (
                    <Badge tone="success">可发布</Badge>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            title="没有匹配 Skill"
            description="换一个关键词，或先去灵感入库拆解好视频并保存为 Skill。"
          />
        )}
      </Card>

      <Card>
        <SectionHeader
          title="Skill 详情"
          description="候选、证据、评测和版本状态在这里复核；只有正式 Skill 才能发布。"
          action={
            focusedTemplate ? (
              <Badge
                tone={
                  focusedTemplate.status === "active"
                    ? "success"
                    : focusedTemplate.status === "candidate"
                      ? "accent"
                      : "warning"
                }
              >
                {statusLabel(focusedTemplate.status)}
              </Badge>
            ) : null
          }
        />
        {focusedTemplate ? (
          <div className="template-detail">
            <div className="template-detail-title">
              <div>
                <span className="eyebrow-text">当前查看</span>
                <strong>{focusedTemplate.name}</strong>
              </div>
              {focusedTemplate.id === selectedTemplateId ? (
                <Badge tone="success">最近保存</Badge>
              ) : (
                <Badge>当前预览</Badge>
              )}
            </div>
            <div className="skill-detail-meta-row">
              <span>添加日期</span>
              <strong>
                {formatSkillCreatedDate(skillAddedDateValue(focusedTemplate))}
              </strong>
              <span>证据数量</span>
              <strong>{sourceEvidenceLabel(focusedTemplate)}</strong>
            </div>
            <div className="chip-row">
              <Badge tone={scoreTone(focusedTemplate.quality_score)}>
                {focusedTemplate.quality_score || 80} 分
              </Badge>
              <Badge
                tone={
                  focusedTemplate.evaluation_summary?.passed
                    ? "success"
                    : "warning"
                }
              >
                {evaluationStatus(focusedTemplate)}
              </Badge>
              {focusedTemplate.hotspot_types.slice(0, 4).map((item) => (
                <Badge key={item}>{item}</Badge>
              ))}
            </div>

            <div
              className="skill-detail-tabs"
              role="tablist"
              aria-label="Skill 详情视图"
            >
              {(
                [
                  ["overview", "用途", BrainCircuit],
                  ["structure", "结构", Layers3],
                  ["sources", "来源", Video],
                  ["evaluation", "评测", FileText],
                  ["manage", "维护", Settings2],
                ] as const
              ).map(([value, label, Icon]) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={detailTab === value}
                  className={detailTab === value ? "is-active" : ""}
                  onClick={() => setDetailTab(value)}
                >
                  <Icon size={15} />
                  {label}
                </button>
              ))}
            </div>

            {detailTab === "overview" ? (
              <div className="skill-detail-panel" role="tabpanel">
                <div className="skill-decision-summary">
                  <span>它最适合解决</span>
                  <strong>{skillProblem(focusedTemplate)}</strong>
                </div>
                <div className="skill-fit-mode-grid">
                  <div>
                    <span>只有主题或想法</span>
                    <strong>
                      AI 判断它能否帮你搭出完整结构，并提示需要补哪些素材。
                    </strong>
                  </div>
                  <div>
                    <span>大纲或半成品</span>
                    <strong>AI 判断稿件缺口是否正好由这个 Skill 补齐。</strong>
                  </div>
                  <div>
                    <span>完整稿件</span>
                    <strong>
                      AI 判断结构是否适配，再决定局部优化还是补充一个新的
                      Skill。
                    </strong>
                  </div>
                </div>
                <div className="detail-block">
                  <span>能补哪些写作缺口</span>
                  <div className="detail-list">
                    {(focusedTemplate.solves_problems?.length
                      ? focusedTemplate.solves_problems
                      : [skillProblem(focusedTemplate)]
                    )
                      .slice(0, 5)
                      .map((item) => (
                        <strong key={item}>{item}</strong>
                      ))}
                  </div>
                </div>
                <div className="detail-block">
                  <span>适合复用的结构条件</span>
                  <div className="detail-list">
                    {(focusedTemplate.applicable_scenes?.length
                      ? focusedTemplate.applicable_scenes
                      : ["待人工补充结构适用条件"]
                    )
                      .slice(0, 6)
                      .map((item) => (
                        <strong key={item}>{item}</strong>
                      ))}
                  </div>
                </div>
                <div className="detail-block skill-match-explainer">
                  <span>AI 辅助判断依据，不是关键词门槛</span>
                  <p>
                    系统会同时看输入类型、创作目标、当前稿件缺口和可补充素材。即使你只输入一个主题，也能按“这个
                    Skill 能否把稿子补完整”进行语义匹配。
                  </p>
                  <div className="chip-row">
                    {skillMatchSignals(focusedTemplate)
                      .slice(0, 8)
                      .map((item) => (
                        <Badge key={item}>{item}</Badge>
                      ))}
                  </div>
                </div>
                <details className="quiet-disclosure">
                  <summary>查看不适用情况</summary>
                  <p>
                    {focusedTemplate.unsuitable_scenes?.join(" / ") ||
                      "暂未记录不适用案例"}
                  </p>
                </details>
              </div>
            ) : null}

            {detailTab === "structure" ? (
              <div className="skill-detail-panel" role="tabpanel">
                <div className="detail-block">
                  <span>结构步骤</span>
                  <ol className="skill-structure-list">
                    {focusedTemplate.skeleton.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ol>
                </div>
                <div className="detail-block">
                  <span>开头钩子</span>
                  <strong>{focusedTemplate.hook_formula}</strong>
                </div>
                <div className="detail-block">
                  <span>情绪节奏</span>
                  <strong>{focusedTemplate.emotion_rhythm}</strong>
                </div>
                <div className="detail-block">
                  <span>结尾公式</span>
                  <strong>{focusedTemplate.ending_formula}</strong>
                </div>
                <div className="detail-block detail-warning">
                  <span>不能碰的边界</span>
                  <strong>{focusedTemplate.risk_boundary}</strong>
                </div>
              </div>
            ) : null}

            {detailTab === "sources" ? (
              <div
                className="skill-detail-panel skill-source-block"
                role="tabpanel"
              >
                <div className="skill-decision-summary">
                  <span>来源证据</span>
                  <strong>
                    {sourceEvidenceCount(focusedTemplate) > 0
                      ? `${sourceEvidenceCount(focusedTemplate)} 个来源共同支持这个写法`
                      : "这条历史 Skill 缺少可追溯来源"}
                  </strong>
                </div>
                {focusedTemplate.sources?.length ? (
                  <div className="skill-source-list">
                    {focusedTemplate.sources.map((source, index) => (
                      <details
                        className="skill-source-item"
                        key={`${source.source_video_id}-${index}`}
                      >
                        <summary>
                          <div>
                            <strong>
                              {source.title || `来源视频 ${index + 1}`}
                            </strong>
                            <small>
                              {source.author || "账号昵称未识别"} ·{" "}
                              {formatRecognizedTime(source.recognized_at)}
                            </small>
                          </div>
                          <FileText size={16} />
                        </summary>
                        <div className="skill-source-meta">
                          <span>原视频作者</span>
                          <strong>{source.author || "未识别"}</strong>
                          <span>提取时间</span>
                          <strong>
                            {formatRecognizedTime(source.recognized_at)}
                          </strong>
                        </div>
                        <div className="skill-source-link">
                          <span>原视频链接</span>
                          {source.url ? (
                            <a
                              href={source.url}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(event) => event.stopPropagation()}
                            >
                              <ExternalLink size={14} />
                              {source.url}
                            </a>
                          ) : (
                            <strong>历史来源未保存原视频链接</strong>
                          )}
                        </div>
                        <div className="skill-source-transcript">
                          <span>原视频提取文稿</span>
                          <p>
                            {source.transcript ||
                              "历史来源未保存完整视频提取文稿。"}
                          </p>
                        </div>
                      </details>
                    ))}
                  </div>
                ) : focusedTemplate.source_titles?.length ? (
                  <small>
                    历史来源仅保留标题：
                    {focusedTemplate.source_titles.join(" / ")}
                    。缺少原视频作者、原视频链接和提取文稿，建议重新从真实视频沉淀一次。
                  </small>
                ) : (
                  <small>
                    这条 Skill
                    没有真实视频来源材料，建议不要发布给团队复用；请重新从原视频链接沉淀，保存作者、链接和提取文稿。
                  </small>
                )}
              </div>
            ) : null}

            {detailTab === "evaluation" ? (
              <div className="skill-detail-panel" role="tabpanel">
                <div className="skill-decision-summary">
                  <span>发布评测</span>
                  <strong>
                    {focusedTemplate.evaluation_summary?.passed
                      ? "required 模式评测已通过"
                      : focusedTemplate.evaluation_summary?.evaluated_at
                        ? "required 模式评测未达标"
                        : "将在申请正式时自动运行 required 模式评测"}
                  </strong>
                </div>
                <div className="skill-fit-mode-grid">
                  <div>
                    <span>路由准确率</span>
                    <strong>
                      {focusedTemplate.evaluation_summary?.routing_accuracy ==
                      null
                        ? "待运行"
                        : `${Math.round(focusedTemplate.evaluation_summary.routing_accuracy * 100)}%`}
                    </strong>
                  </div>
                  <div>
                    <span>无匹配识别</span>
                    <strong>
                      {focusedTemplate.evaluation_summary?.no_match_accuracy ==
                      null
                        ? "待运行"
                        : `${Math.round(focusedTemplate.evaluation_summary.no_match_accuracy * 100)}%`}
                    </strong>
                  </div>
                  <div>
                    <span>人工均分</span>
                    <strong>
                      {focusedTemplate.evaluation_summary?.human_score == null
                        ? "待盲审"
                        : `${focusedTemplate.evaluation_summary.human_score.toFixed(1)} / 5`}
                    </strong>
                  </div>
                </div>
                <div className="detail-block">
                  <span>版本追溯</span>
                  <strong>
                    v{focusedTemplate.version || 1} · 最近复审{" "}
                    {formatSkillCreatedDate(focusedTemplate.reviewed_at)}
                  </strong>
                </div>
              </div>
            ) : null}

            {detailTab === "manage" ? (
              <div className="skill-detail-panel" role="tabpanel">
                {focusedTemplate.disabled_reason ? (
                  <div className="alert-box alert-warning">
                    <strong>Skill 已停用</strong>
                    <span>{focusedTemplate.disabled_reason}</span>
                  </div>
                ) : null}
                <div className="detail-block">
                  <span>治理状态</span>
                  <strong>
                    {statusLabel(focusedTemplate.status)} · v
                    {focusedTemplate.version || 1} ·{" "}
                    {focusedTemplate.owner || "内容主审"}
                  </strong>
                </div>
                <div className="detail-block">
                  <span>下一步</span>
                  <strong>
                    {needsSourcePreparation
                      ? sourceRemaining > 0
                        ? `再补充 ${sourceRemaining} 条同结构来源后即可检查发布。`
                        : "补充一条带完整文稿的结构来源后即可检查发布。"
                      : "来源已齐备；点击后会自动完成评测、主审确认和 GitHub 同步。"}
                  </strong>
                </div>
                {promotionReadiness ? (
                  <div
                    className={`alert-box ${needsSourcePreparation ? "alert-warning" : "alert-success"}`}
                    aria-live="polite"
                  >
                    <strong>
                      {needsSourcePreparation
                        ? sourceRemaining > 0
                          ? `还差 ${sourceRemaining} 条同结构来源`
                          : "还需要可追溯的结构来源"
                        : "已具备申请正式的素材条件"}
                    </strong>
                    <p>
                      来源 {promotionReadiness.source_count}/
                      {promotionReadiness.required_source_count}；结构证据{" "}
                      {promotionReadiness.has_structure_evidence ? "已记录" : "缺失"}
                    </p>
                    <p>
                      {needsSourcePreparation
                        ? "每补充一条来源，系统都会保存原视频、作者、链接和提取文稿；保存时会自动归到当前 Skill。"
                        : "点击检查后，系统会运行真实模型评测，记录本次主审批准，再同步稳定包到 GitHub。"}
                    </p>
                  </div>
                ) : (
                  <div className="detail-block">
                    <span>正式发布资格</span>
                    <strong>正在读取...</strong>
                  </div>
                )}
                <div className="button-row">
                  {focusedTemplate.status === "candidate" ? (
                    <>
                      {needsSourcePreparation ? (
                        <button
                          type="button"
                          className="primary-button"
                          disabled={governanceSaving}
                          onClick={() => onContinueEvidence(focusedTemplate)}
                        >
                          {sourceRemaining > 0
                            ? `补充同类来源（还需 ${sourceRemaining} 条）`
                            : "补充可追溯来源"}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="primary-button"
                          disabled={governanceSaving || !promotionReadiness}
                          onClick={() => void approveAndPublish()}
                        >
                          {governanceSaving
                            ? "正在评测并同步..."
                            : "检查并申请正式并同步 GitHub"}
                        </button>
                      )}
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={governanceSaving}
                        onClick={() => void updateStatus("paused")}
                      >
                        暂停路由
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={governanceSaving}
                        onClick={() => void updateStatus("retired")}
                      >
                        退役保留历史
                      </button>
                    </>
                  ) : null}
                  {focusedTemplate.status === "active" ? (
                    <>
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={governanceSaving}
                        onClick={() => void updateStatus("paused")}
                      >
                        暂停路由
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={governanceSaving}
                        onClick={() => void updateStatus("retired")}
                      >
                        退役保留历史
                      </button>
                    </>
                  ) : null}
                  {focusedTemplate.status === "paused" ? (
                    <>
                      <button
                        type="button"
                        className="primary-button"
                        disabled={governanceSaving}
                        onClick={() => void updateStatus("active")}
                      >
                        恢复路由
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={governanceSaving}
                        onClick={() => void updateStatus("candidate")}
                      >
                        转为候选
                      </button>
                      <button
                        type="button"
                        className="ghost-button"
                        disabled={governanceSaving}
                        onClick={() => void updateStatus("retired")}
                      >
                        退役保留历史
                      </button>
                    </>
                  ) : null}
                  {focusedTemplate.status === "retired" ? (
                    <small>
                      该 Skill 已退役，仅保留历史记录，不能恢复路由或再次发布。
                    </small>
                  ) : null}
                </div>
                {reviewError ? (
                  <div className="alert-box alert-error" role="alert">
                    {reviewError}
                  </div>
                ) : null}
                <div className="detail-block">
                  <span>复盘备注</span>
                  <strong>
                    {focusedTemplate.last_review_note ||
                      "暂未复盘，建议在实际套用后补充质量判断。"}
                  </strong>
                </div>
                <div className="review-editor">
                  <div className="review-editor-header">
                    <div>
                      <span className="eyebrow-text">Skill 复盘</span>
                      <strong>
                        {isEditing
                          ? "编辑质量和适用边界"
                          : "质量分、适用场景和停用状态可人工维护"}
                      </strong>
                    </div>
                    <button
                      type="button"
                      className="secondary-button compact-button"
                      onClick={() => {
                        setReviewDraft(draftFromTemplate(focusedTemplate))
                        setReviewError(null)
                        setIsEditing((current) => !current)
                      }}
                    >
                      {isEditing ? (
                        <RotateCcw size={15} />
                      ) : (
                        <SlidersHorizontal size={15} />
                      )}
                      {isEditing ? "取消编辑" : "编辑复盘"}
                    </button>
                  </div>
                  {isEditing && reviewDraft ? (
                    <div className="review-form">
                      <label>
                        <span>质量分</span>
                        <div className="score-input-row">
                          <input
                            type="range"
                            min={0}
                            max={100}
                            value={reviewDraft.quality_score}
                            onChange={(event) =>
                              setReviewDraft({
                                ...reviewDraft,
                                quality_score: Number(event.target.value),
                              })
                            }
                          />
                          <input
                            type="number"
                            min={0}
                            max={100}
                            value={reviewDraft.quality_score}
                            onChange={(event) =>
                              setReviewDraft({
                                ...reviewDraft,
                                quality_score: Number(event.target.value),
                              })
                            }
                          />
                        </div>
                      </label>
                      <label>
                        <span>适用稿件</span>
                        <textarea
                          value={reviewDraft.applicable_scenes_text}
                          onChange={(event) =>
                            setReviewDraft({
                              ...reviewDraft,
                              applicable_scenes_text: event.target.value,
                            })
                          }
                          placeholder="每行一个，例如：公开回应"
                        />
                      </label>
                      <label>
                        <span>不适用场景</span>
                        <textarea
                          value={reviewDraft.unsuitable_scenes_text}
                          onChange={(event) =>
                            setReviewDraft({
                              ...reviewDraft,
                              unsuitable_scenes_text: event.target.value,
                            })
                          }
                          placeholder="每行一个，例如：未证实恋情"
                        />
                      </label>
                      <label>
                        <span>停用原因</span>
                        <textarea
                          value={reviewDraft.disabled_reason}
                          onChange={(event) =>
                            setReviewDraft({
                              ...reviewDraft,
                              disabled_reason: event.target.value,
                            })
                          }
                          placeholder="留空表示启用；填写原因后发布给团队时会排除该 Skill"
                        />
                      </label>
                      <label>
                        <span>复盘备注</span>
                        <textarea
                          value={reviewDraft.last_review_note}
                          onChange={(event) =>
                            setReviewDraft({
                              ...reviewDraft,
                              last_review_note: event.target.value,
                            })
                          }
                          placeholder="记录适用/不适用案例、表现判断和下次套用提醒"
                        />
                      </label>
                      {reviewError ? (
                        <div className="alert-box alert-error">
                          {reviewError}
                        </div>
                      ) : null}
                      <button
                        type="button"
                        className="primary-button wide-button"
                        disabled={reviewSaving}
                        onClick={saveReview}
                      >
                        <Save size={16} />
                        {reviewSaving ? "保存中..." : "保存复盘"}
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <EmptyState
            title="没有 Skill 详情"
            description="先选择左侧表格中的一个写作 Skill。"
          />
        )}
      </Card>
    </div>
  )
}
