import {
  ArrowLeft,
  ArrowRight,
  Check,
  CircleAlert,
  Copy,
  Download,
  LoaderCircle,
  Plus,
  Search,
  Sparkles,
} from "lucide-react"
import { type ReactNode, useEffect, useRef, useState } from "react"
import {
  generateCompleteScript,
  prepareResearch,
  recommendStructures,
  researchAngleMaterials,
} from "@/api/workbench"
import {
  estimatedSpeechSeconds,
  speechCharacterCount,
  speechLengthStatus,
} from "@/lib/speech"
import {
  angleRequiredSteps,
  buildWritingProjectExport,
  buildWritingProjectMarkdown,
  candidateMaterials,
  hasSelectedAngle,
  materialSelectionSummary,
  selectedAngleText,
  selectedMaterialCards,
  selectedMaterialCardsForRequest,
  writingProjectSteps,
} from "@/lib/writingProject"
import type {
  MaterialCard,
  ScriptGenerationPayload,
  StructureRecommendation,
  TemplatePattern,
  WritingProjectState,
  WritingProjectStep,
} from "@/types/workbench"
import { Badge, Card } from "./ui"

/**
 * WritingProject 创作主线流程壳（Phase 1）。
 *
 * - 默认首页：新建稿件（选题 → 开始研究）。
 * - 项目内：选题 → 研究 → 角度 → 素材 → 结构 → 成稿 → 审稿 → 导出。
 * - 研究步骤走 `POST /research/briefs`（Phase 2：联网研究 + 角度）。
 * - 素材步骤走 `POST /research/materials`（Phase 3：围绕已选角度的第二轮定向研究）。
 * - 结构步骤走 `POST /structures/recommend`（Phase 3：基于已选角度 + 已选素材）。
 * - 成稿 / 审稿仍是流程占位：Phase 4–5 再接入完整成稿与 AI 痕迹标注。
 * - 所有步骤状态保存在 App 内存中的 WritingProjectState，前进 / 后退不丢状态。
 *
 * 过渡说明：旧「写作结构工作稿」生成链路（HotspotStudio / drafts rewrite）
 * 仍在仓库中保留（legacy），Phase 1 不再从主流程调用。
 */

const genericStructure = {
  id: "generic-structure",
  name: "通用写作骨架",
  description: "没有匹配到现成结构时使用，保证写稿不会被 Skill 匹配阻塞。",
  skeleton: ["开头钩子", "事实与细节", "推进与转折", "观点收束", "互动引导"],
  hook_formula: "先给观众一个停下来的理由，再交代必要背景。",
  emotion_rhythm: "好奇 → 理解 → 判断",
  ending_formula: "用一句克制的判断或开放问题收束。",
}

function riskLevelLabel(check: WritingProjectState["evidenceCheck"]) {
  if (!check) return "未执行"
  if (check.passed) return "通过（Low）"
  if (check.unsupported_claims.length) return "需确认（Must Fix / Warning）"
  return "需确认"
}

const materialTypeLabels: Record<string, string> = {
  fact: "事实",
  quote: "引语",
  opinion: "观点",
  case: "案例",
  data: "数据",
  background: "背景",
  comparison: "对比",
}

/**
 * 素材卡状态标签。
 * 观点 / 引语类素材即使来源可追溯，也不显示为「已核实事实」，
 * 避免把「网友这么认为」读成「事情就是这样」。
 */
function verificationLabel(card: MaterialCard) {
  const isOpinion = card.type === "opinion" || card.type === "quote"
  if (card.verification_status === "verified") {
    return isOpinion
      ? { text: "观点 · 来源可追溯", tone: "neutral" as const }
      : { text: "来源已核实", tone: "success" as const }
  }
  if (card.verification_status === "preview") {
    return { text: "研究预览", tone: "warning" as const }
  }
  return isOpinion
    ? { text: "观点 · 待核实", tone: "warning" as const }
    : { text: "待核实", tone: "warning" as const }
}

function StepFooter({
  onBack,
  nextLabel,
  onNext,
  extra,
}: {
  onBack?: () => void
  nextLabel?: string
  onNext?: () => void
  extra?: ReactNode
}) {
  return (
    <div className="workflow-actions">
      {onBack ? (
        <button type="button" className="secondary-button" onClick={onBack}>
          <ArrowLeft size={15} />
          返回上一步
        </button>
      ) : (
        <span />
      )}
      <div>
        {extra}
        {onNext && nextLabel ? (
          <button type="button" className="primary-button" onClick={onNext}>
            {nextLabel}
            <ArrowRight size={15} />
          </button>
        ) : null}
      </div>
    </div>
  )
}

export function ContentWorkflow({
  project,
  templates,
  onStartProject,
  onProjectChange,
  onNewProject,
  onOpenStructures,
  onToast,
}: {
  project: WritingProjectState | null
  templates: TemplatePattern[]
  onStartProject: (topic: string, supplement: string) => WritingProjectState
  onProjectChange: (
    projectId: string,
    patch: Partial<WritingProjectState>,
  ) => void
  onNewProject: () => void
  onOpenStructures: () => void
  onToast: (message: string) => void
}) {
  const [topicDraft, setTopicDraft] = useState("")
  const [supplementDraft, setSupplementDraft] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 结构推荐的惰性请求状态（useRef/useEffect 必须位于任何 early return 之前）。
  const structureFetchKeyRef = useRef("")


  const runResearch = async (topic: string, supplement: string, projectId: string) => {
    setBusy(true)
    setError(null)
    onProjectChange(projectId, {
      step: "research",
      researchStatus: "running",
      researchError: null,
    })
    try {
      const response = await prepareResearch({
        topic,
        material_text: supplement,
        account_type: project?.settings.accountType || "娱乐吃瓜号",
        duration_seconds: project?.settings.durationSeconds || 60,
        tone: project?.settings.tone || "真人口语",
        goal: project?.settings.goal || "引发讨论",
      })
      onProjectChange(projectId, {
        research: response,
        researchStatus: "done",
        researchError: null,
        step: "research",
        // 角度是强制人工决策：不预选，必须由用户选择或自定义。
        selectedAngleId: "",
        customAngle: "",
        angleMode: "recommended",
        // 角度与素材都必须在研究之后重新确认，重新研究时清空下游状态。
        materialStatus: "idle",
        materialError: null,
        materialCards: [],
        materialStopReason: "",
        materialGuidance: "",
        materialModel: null,
        selectedMaterialKeys: [],
        structureRecommendations: [],
        structureGeneric: null,
        structureNote: "",
        structureStatus: "idle",
        structureError: null,
        selectedStructureId: "",
        structureMode: "generic",
        draftStatus: "idle",
        draftError: null,
        draftTitle: "",
        draftText: "",
        draftVersions: [],
        materialGaps: [],
        evidenceMap: [],
        evidenceCheck: null,
      })
    } catch (cause) {
      onProjectChange(projectId, {
        researchStatus: "error",
        researchError:
          cause instanceof Error ? cause.message : "研究简报生成失败，请重试。",
      })
    } finally {
      setBusy(false)
    }
  }

  const startResearch = async () => {
    const topic = topicDraft.trim()
    if (topic.length < 4) {
      setError("选题至少写清楚 4 个字，例如一条事件或一个待讨论的话题。")
      return
    }
    const created = onStartProject(topic, supplementDraft.trim())
    await runResearch(created.topic, created.supplement, created.id)
  }

  // Phase 3：结构推荐基于 SelectedAngle + SelectedMaterials，在进入结构步骤时惰性请求。
  useEffect(() => {
    if (!project || project.step !== "structure") return
    if (!hasSelectedAngle(project)) return
    if (project.structureStatus === "loading") return
    if (project.structureStatus === "done") return
    const angleText = selectedAngleText(project)
    const selected = selectedMaterialCardsForRequest(project)
    const fetchKey = `${project.id}:${angleText}:${selected
      .map((item) => item.id)
      .join(",")}`
    if (structureFetchKeyRef.current === fetchKey) return
    structureFetchKeyRef.current = fetchKey
    onProjectChange(project.id, {
      structureStatus: "loading",
      structureError: null,
    })
    recommendStructures({
      topic: project.topic,
      selected_angle: angleText,
      materials: selected,
      account_type: project.settings.accountType,
      duration_seconds: project.settings.durationSeconds,
      tone: project.settings.tone,
      goal: project.settings.goal,
      research_summary: project.research?.research_brief.summary || "",
    })
      .then((response) => {
        // project 对象会随每次状态更新变化；只要这次请求仍是最新请求就应用结果。
        if (structureFetchKeyRef.current !== fetchKey) return
        onProjectChange(project.id, {
          structureRecommendations: response.recommendations,
          structureGeneric: response.generic_structure,
          structureNote: response.note,
          structureStatus: "done",
          structureError: null,
          structureMode: response.recommendations.length
            ? "recommended"
            : "generic",
          selectedStructureId:
            response.recommendations[0]?.id || response.generic_structure.id,
        })
      })
      .catch((cause) => {
        if (structureFetchKeyRef.current !== fetchKey) return
        onProjectChange(project.id, {
          structureRecommendations: [],
          structureStatus: "error",
          structureError:
            cause instanceof Error
              ? cause.message
              : "结构推荐失败，可直接使用通用结构。",
          structureMode: "generic",
          selectedStructureId: "generic-structure",
        })
      })
  }, [onProjectChange, project])

  if (!project) {
    return (
      <div className="page-grid">
        <Card className="workflow-panel writing-project-start">
          <div className="writing-start-head">
            <p className="section-eyebrow">新建稿件</p>
            <h1>你要写什么？</h1>
            <p>
              写下今天要写的选题，或者补充你已经有的事实、链接和客户要求。
              研究、角度、素材和结构都会在后面的步骤里逐步确认。
            </p>
          </div>
          {error ? (
            <div className="alert-box alert-error" role="alert">
              <CircleAlert size={15} />
              <span>{error}</span>
            </div>
          ) : null}
          <label className="writing-topic-field">
            <span>你要写什么？</span>
            <textarea
              aria-label="你要写什么？"
              value={topicDraft}
              onChange={(event) => setTopicDraft(event.target.value)}
              placeholder="例如：某明星公开回应为什么引发两种完全不同的反应？"
            />
          </label>
          <label className="writing-topic-field">
            <span>补充材料（可选）</span>
            <textarea
              aria-label="补充材料（可选）"
              value={supplementDraft}
              onChange={(event) => setSupplementDraft(event.target.value)}
              placeholder="已有事实、链接、截图里的文字、客户要求或禁用表达。没有也可以直接开始研究。"
            />
          </label>
          <div className="workflow-actions">
            <span>
              <Search size={15} />
              没有素材也可以继续，研究简报会明确标出待核实项。
            </span>
            <button
              type="button"
              className="primary-button"
              onClick={() => void startResearch()}
              disabled={busy}
            >
              {busy ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Search size={16} />
              )}
              {busy ? "正在开始研究" : "开始研究"}
            </button>
          </div>
        </Card>
      </div>
    )
  }

  const research = project.research
  const brief = research?.research_brief || null
  const angles = research?.angle_candidates || []
  const structureOptions: StructureRecommendation[] = project.structureGeneric
    ? [...project.structureRecommendations, project.structureGeneric]
    : project.structureRecommendations
  const currentStructure =
    structureOptions.find((item) => item.id === project.selectedStructureId) ||
    structureOptions[0] ||
    null
  const structureName = currentStructure?.name || genericStructure.name
  const structureSkeleton = currentStructure?.skeleton || genericStructure.skeleton
  const materials = candidateMaterials(project)
  const materialCards = project.materialCards
  const selectedCards = selectedMaterialCards(project)
  const selection = materialSelectionSummary(project)
  const selectedMaterialTexts = selectedCards.map(
    (item) => `${item.title}（${materialTypeLabels[item.type] || item.type}）`,
  )
  const selectedAngle = selectedAngleText(project)
  const draftLength = speechLengthStatus(
    project.draftText,
    project.settings.durationSeconds,
  )
  const lengthHint =
    draftLength.status === "short"
      ? "比参考时长偏短（不做注水要求）"
      : draftLength.status === "long"
        ? "比参考时长偏长，可自行精简"
        : "与参考时长接近"
  const claims = brief?.verified_claims || []
  const sourceById = new Map(
    (brief?.sources || []).map((source, index) => [
      source.id || `src-${index + 1}`,
      source,
    ]),
  )

  const currentIndex = writingProjectSteps.findIndex(
    (item) => item.id === project.step,
  )
  const goToStep = (step: WritingProjectStep) => {
    setError(null)
    // 角度是强制决策节点：没有 SelectedAngle 就不能进入素材及之后的步骤。
    if (angleRequiredSteps.includes(step) && !hasSelectedAngle(project)) {
      setError(
        "进入素材阶段前必须先确认内容角度：选择一个推荐角度，或切换到「我来定义」并写清楚自己的角度。",
      )
      onProjectChange(project.id, { step: "angle" })
      return
    }
    if (step === "angle" && project.researchStatus !== "done") {
      setError("还没有研究简报：先完成研究，再确认内容角度。")
      onProjectChange(project.id, { step: "research" })
      return
    }
    onProjectChange(project.id, { step })
  }
  const goNext = () => {
    setError(null)
    const next = writingProjectSteps[currentIndex + 1]
    if (next) goToStep(next.id)
  }
  const goBack = () => {
    setError(null)
    const previous = writingProjectSteps[currentIndex - 1]
    if (previous) onProjectChange(project.id, { step: previous.id })
  }
  const runMaterialResearch = async () => {
    if (!hasSelectedAngle(project)) {
      setError("请先确认内容角度，再开始定向素材研究。")
      return
    }
    const angleText = selectedAngleText(project)
    const angleCard =
      project.angleMode === "recommended"
        ? angles.find((item) => item.id === project.selectedAngleId)
        : undefined
    onProjectChange(project.id, {
      materialStatus: "running",
      materialError: null,
    })
    try {
      const response = await researchAngleMaterials({
        topic: project.topic,
        material_text: project.supplement,
        account_type: project.settings.accountType,
        duration_seconds: project.settings.durationSeconds,
        tone: project.settings.tone,
        goal: project.settings.goal,
        selected_angle: angleText,
        angle_name: angleCard?.name || "",
        angle_missing_evidence:
          angleCard?.evidence?.missing_evidence ||
          angleCard?.missing_materials ||
          [],
        research_brief: project.research?.research_brief || null,
      })
      const cards = response.materials.map((item) => ({
        ...item,
        selected: false,
      }))
      onProjectChange(project.id, {
        materialCards: cards,
        materialStatus: "done",
        materialError: null,
        materialStopReason: response.stop_reason,
        materialGuidance: response.guidance,
        materialModel: response.research_model ?? null,
        // 用户必须显式选择；默认不替用户勾选任何素材。
        selectedMaterialKeys: [],
        // 素材变化后结构推荐需要重新计算。
        structureRecommendations: [],
        structureGeneric: null,
        structureNote: "",
        structureStatus: "idle",
        structureError: null,
        selectedStructureId: "",
        structureMode: "generic",
      })
    } catch (cause) {
      onProjectChange(project.id, {
        materialStatus: "error",
        materialError:
          cause instanceof Error ? cause.message : "定向素材研究失败，请重试。",
      })
    }
  }

  const toggleMaterialCard = (materialId: string) => {
    const next = project.selectedMaterialKeys.includes(materialId)
      ? project.selectedMaterialKeys.filter((item) => item !== materialId)
      : [...project.selectedMaterialKeys, materialId]
    onProjectChange(project.id, {
      selectedMaterialKeys: next,
      // 选择变化后结构推荐失效，下一次进入结构步骤会重新推荐。
      structureRecommendations: [],
      structureGeneric: null,
      structureStatus: "idle",
      structureError: null,
    })
    structureFetchKeyRef.current = ""
  }

  const selectAllMaterials = (checked: boolean) => {
    onProjectChange(project.id, {
      selectedMaterialKeys: checked
        ? project.materialCards.map((item) => item.id)
        : [],
      structureRecommendations: [],
      structureGeneric: null,
      structureStatus: "idle",
      structureError: null,
    })
    structureFetchKeyRef.current = ""
  }

  const runDraftGeneration = async () => {
    if (!hasSelectedAngle(project)) {
      setError("请先确认内容角度，再生成完整初稿。")
      return
    }
    const angleText = selectedAngleText(project)
    const structure = currentStructure
    const payload: ScriptGenerationPayload = {
      topic: project.topic,
      user_material: project.supplement,
      selected_angle: angleText,
      angle_name:
        project.angleMode === "recommended"
          ? angles.find((item) => item.id === project.selectedAngleId)?.name || ""
          : "",
      structure_id: structure?.id || "generic-structure",
      structure_name: structure?.name || genericStructure.name,
      structure_steps: structure?.skeleton || genericStructure.skeleton,
      structure_mapping: structure?.material_mapping || [],
      structure_gaps: structure?.material_gaps || [],
      materials: selectedMaterialCardsForRequest(project),
      research_brief: project.research?.research_brief || null,
      account_type: project.settings.accountType,
      duration_seconds: project.settings.durationSeconds,
      tone: project.settings.tone,
      goal: project.settings.goal,
    }
    onProjectChange(project.id, {
      draftStatus: "running",
      draftError: null,
    })
    try {
      const response = await generateCompleteScript(payload)
      const script = response.script
      const nextVersion = {
        id: `${script.id}-v${project.draftVersions.length + 1}`,
        label: `v${project.draftVersions.length + 1}`,
        title: script.title,
        text: script.spoken_script,
        savedAt: new Date().toISOString(),
      }
      onProjectChange(project.id, {
        draftStatus: "done",
        draftError: null,
        draftTitle: script.title,
        draftText: script.spoken_script,
        draftGenerationNote: response.note,
        draftModel: response.model ?? null,
        titleCandidates: script.title_candidates || [],
        shotSuggestions: script.shot_suggestions || [],
        subtitleRhythm: script.subtitle_rhythm || [],
        commentCta: script.comment_cta || "",
        usedMaterialIds: script.used_material_ids || [],
        usedClaimIds: script.used_claim_ids || [],
        materialGaps: script.material_gaps || [],
        evidenceMap: script.evidence_map || [],
        evidenceCheck: script.evidence_check || null,
        structureCoverage: script.structure_coverage || [],
        draftVersions: [nextVersion],
      })
    } catch (cause) {
      onProjectChange(project.id, {
        draftStatus: "error",
        draftError:
          cause instanceof Error ? cause.message : "初稿生成失败，请重试。",
      })
    }
  }

  const saveDraftVersion = () => {
    const label = `v${project.draftVersions.length + 1}`
    onProjectChange(project.id, {
      draftVersions: [
        ...project.draftVersions,
        {
          id: `${project.id}-${Date.now().toString(36)}`,
          label,
          title: project.draftTitle,
          text: project.draftText,
          savedAt: new Date().toISOString(),
        },
      ],
    })
    onToast(`已保存 ${label}`)
  }

  const restoreDraftVersion = (versionId: string) => {
    const version = project.draftVersions.find((item) => item.id === versionId)
    if (!version) return
    onProjectChange(project.id, {
      draftTitle: version.title,
      draftText: version.text,
    })
    onToast(`已恢复到 ${version.label}`)
  }

  const confirmAngle = () => {
    if (project.angleMode === "recommended" && !project.selectedAngleId) {
      setError("必须先选中一个推荐角度才能继续；不能跳过角度直接进入素材。")
      return
    }
    if (
      project.angleMode === "custom" &&
      project.customAngle.trim().length < 6
    ) {
      setError("自定义角度至少写清楚一个完整判断。")
      return
    }
    if (!hasSelectedAngle(project)) {
      setError("进入素材阶段前必须存在已选角度（SelectedAngle）。")
      return
    }
    goNext()
  }
  const toggleReviewCheck = (checkId: string) => {
    onProjectChange(project.id, {
      reviewChecks: project.reviewChecks.map((check) =>
        check.id === checkId ? { ...check, checked: !check.checked } : check,
      ),
    })
  }

  const exportMarkdown = () =>
    buildWritingProjectMarkdown(
      project,
      structureName,
      structureSkeleton,
      selectedAngle,
      selectedMaterialTexts,
    )

  const markExported = () => {
    onProjectChange(project.id, { exportedAt: new Date().toISOString() })
  }

  const copyMarkdown = async () => {
    try {
      await navigator.clipboard.writeText(exportMarkdown())
      markExported()
      onToast("已复制 Markdown 稿件。")
    } catch {
      onToast("浏览器未允许复制，请改用下载。")
    }
  }

  const downloadFile = (filename: string, content: string, mime: string) => {
    const blob = new Blob([content], { type: mime })
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    link.click()
    URL.revokeObjectURL(url)
    markExported()
    onToast(`已导出 ${filename}`)
  }

  const safeFilename =
    (project.topic.slice(0, 20).replace(/[\\/:*?"<>|\s]+/g, "-") || "writing-project")

  return (
    <div className="page-grid">
      <Card className="workflow-panel writing-project-shell">
        <div className="writing-project-head">
          <div>
            <p className="section-eyebrow">稿件项目</p>
            <h2>{project.topic}</h2>
            <p>
              当前步骤：{writingProjectSteps[currentIndex]?.label || project.step}
              ，状态会随步骤保留，可随时返回修改。
            </p>
          </div>
          <button type="button" className="text-button" onClick={onNewProject}>
            <Plus size={14} />
            新建另一篇
          </button>
        </div>

        <div className="workflow-stepper is-writing-project" aria-label="创作流程步骤">
          {writingProjectSteps.map((item, index) => (
            <button
              type="button"
              key={item.id}
              className={`workflow-step ${item.id === project.step ? "is-active" : ""} ${index < currentIndex ? "is-done" : ""}`}
              onClick={() => goToStep(item.id)}
            >
              <span>{index + 1}</span>
              {item.label}
            </button>
          ))}
        </div>

        {error ? (
          <div className="alert-box alert-error" role="alert">
            <CircleAlert size={15} />
            <span>{error}</span>
          </div>
        ) : null}

        {project.step === "topic" ? (
          <div className="writing-panel">
            <label className="writing-topic-field">
              <span>你要写什么？</span>
              <textarea
                aria-label="选题"
                value={project.topic}
                onChange={(event) =>
                  onProjectChange(project.id, { topic: event.target.value })
                }
              />
            </label>
            <label className="writing-topic-field">
              <span>补充材料（可选）</span>
              <textarea
                aria-label="补充材料"
                value={project.supplement}
                onChange={(event) =>
                  onProjectChange(project.id, { supplement: event.target.value })
                }
                placeholder="已有事实、链接、截图里的文字、客户要求或禁用表达。"
              />
            </label>
            <div className="workflow-actions">
              <span />
              <button
                type="button"
                className="primary-button"
                onClick={() =>
                  void runResearch(project.topic, project.supplement, project.id)
                }
                disabled={busy || project.topic.trim().length < 4}
              >
                {busy ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Search size={16} />
                )}
                {project.research ? "重新研究" : "开始研究"}
              </button>
            </div>
          </div>
        ) : null}

        {project.step === "research" ? (
          project.researchStatus === "running" ? (
            <div className="writing-panel">
              <div className="workflow-task-line" role="status">
                <LoaderCircle className="spin" size={15} />
                正在整理研究简报
              </div>
            </div>
          ) : project.researchStatus === "error" ? (
            <div className="writing-panel">
              <div className="alert-box alert-error" role="alert">
                <CircleAlert size={15} />
                <span>{project.researchError || "研究失败，请重试。"}</span>
              </div>
              <StepFooter
                onBack={goBack}
                nextLabel="重新研究"
                onNext={() =>
                  void runResearch(project.topic, project.supplement, project.id)
                }
              />
            </div>
          ) : brief ? (
            (() => {
              const verified = brief.verification_status === "verified"
              const factLabel = verified
                ? "已确认事实"
                : "事实候选 / 用户提供的信息"
              const pendingItems = [
                ...(brief.uncertain_claims || []),
                ...brief.research_gap,
              ]
              return (
                <div className="workflow-review-grid">
                  <section>
                    <h3>研究简报</h3>
                    {verified ? (
                      <p className="workflow-summary">
                        已联网核对 {brief.sources.length} 个来源，以下事实可直接作为写作依据。
                      </p>
                    ) : (
                      <div className="workflow-warning">
                        <CircleAlert size={15} />
                        <div>
                          <strong>当前为研究预览，尚未完成联网事实核验</strong>
                          <span>
                            {brief.verification_note ||
                              "下面内容只是根据你的输入整理的事实候选，写入正文前必须自行核实。"}
                          </span>
                        </div>
                      </div>
                    )}
                    {brief.summary ? (
                      <p className="workflow-summary">{brief.summary}</p>
                    ) : null}
                    <strong className="writing-fact-label">{factLabel}</strong>
                    {claims.length ? (
                      <ul className="claim-list">
                        {claims.map((claim) => (
                          <li key={claim.id}>
                            <div className="claim-head">
                              <Check size={14} />
                              <span>{claim.claim}</span>
                            </div>
                            <div className="claim-sources">
                              <small>
                                支持来源
                                {claim.confidence !== "high"
                                  ? `（置信度 ${claim.confidence === "medium" ? "中" : "低"}）`
                                  : ""}
                                ：
                              </small>
                              {claim.source_ids.length ? (
                                claim.source_ids.map((sourceId) => {
                                  const source = sourceById.get(sourceId)
                                  if (!source) {
                                    return <span key={sourceId}>{sourceId}</span>
                                  }
                                  return (
                                    <a
                                      key={sourceId}
                                      href={source.url}
                                      target="_blank"
                                      rel="noreferrer"
                                    >
                                      {source.publisher || source.title}
                                    </a>
                                  )
                                })
                              ) : (
                                <span>未标注来源</span>
                              )}
                              {claim.note ? <em>{claim.note}</em> : null}
                            </div>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="workflow-fact-list">
                        {(
                          brief.verified_facts.length
                            ? brief.verified_facts
                            : [
                                "暂无可写入正文的信息：请补充可核实材料，或只用个人判断表达。",
                              ]
                        ).map((fact) => (
                          <div key={fact}>
                            <Check size={14} />
                            <span>{fact}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    {pendingItems.length ? (
                      <div className="workflow-warning">
                        <CircleAlert size={15} />
                        <div>
                          <strong>待核验信息</strong>
                          {pendingItems.map((item) => (
                            <span key={item}>{item}</span>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {brief.opinions?.length || brief.controversies?.length ? (
                      <>
                        <strong className="writing-fact-label">
                          观点与争议（不等于事实）
                        </strong>
                        <div className="workflow-meta-list">
                          {[...(brief.opinions || []), ...(brief.controversies || [])].map(
                            (item) => (
                              <span key={item}>{item}</span>
                            ),
                          )}
                        </div>
                      </>
                    ) : null}
                    {brief.risk_flags.length ? (
                      <div className="workflow-warning">
                        <CircleAlert size={15} />
                        <div>
                          <strong>研究阶段风险提示</strong>
                          {brief.risk_flags.map((item) => (
                            <span key={item}>{item}</span>
                          ))}
                        </div>
                      </div>
                    ) : null}
                  </section>
                  <section>
                    <h3>背景与来源</h3>
                    <div className="workflow-meta-list">
                      {brief.audience_sentiment ? (
                        <span>公众情绪：{brief.audience_sentiment}</span>
                      ) : null}
                      {[...brief.timeline, ...brief.platform_context].map((item) => (
                        <span key={item}>{item}</span>
                      ))}
                    </div>
                    {brief.sources.length ? (
                      <div className="workflow-source-list">
                        {brief.sources.map((source) => (
                          <a
                            key={`${source.url}-${source.title}`}
                            href={source.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            <strong>{source.title}</strong>
                            <small>
                              {source.publisher ? `${source.publisher} · ` : ""}
                              {source.published_at || ""}
                            </small>
                            <em>{source.url}</em>
                          </a>
                        ))}
                      </div>
                    ) : (
                      <p className="workflow-summary">
                        本次没有可引用的公开来源；涉及当前事件时请先补充链接再进入成稿。
                      </p>
                    )}
                    <StepFooter nextLabel="确认进入角度" onNext={goNext} />
                  </section>
                </div>
              )
            })()
          ) : (
            <div className="writing-panel">
              <div className="workflow-warning">
                <CircleAlert size={15} />
                <div>
                  <strong>还没有研究简报</strong>
                  <span>回到选题步骤，点击“开始研究”生成研究简报。</span>
                </div>
              </div>
              <StepFooter onBack={goBack} />
            </div>
          )
        ) : null}

        {project.step === "angle" ? (
          <div className="writing-panel">
            <p className="workflow-summary">
              角度是本流程的强制决策节点：必须选择系统推荐角度，或自己写清楚角度，
              才能进入素材和结构。角度确定之后才会匹配写作结构。
            </p>
            <div className="workflow-option-tabs">
              <button
                type="button"
                className={project.angleMode === "recommended" ? "is-active" : ""}
                onClick={() =>
                  onProjectChange(project.id, { angleMode: "recommended" })
                }
              >
                系统推荐
              </button>
              <button
                type="button"
                className={project.angleMode === "custom" ? "is-active" : ""}
                onClick={() => onProjectChange(project.id, { angleMode: "custom" })}
              >
                我来定义
              </button>
            </div>
            {project.angleMode === "recommended" ? (
              angles.length ? (
                <div className="workflow-choice-list">
                  {angles.map((angle) => {
                    const selected = project.selectedAngleId === angle.id
                    return (
                      <button
                        type="button"
                        key={angle.id}
                        className={`workflow-choice ${selected ? "is-selected" : ""}`}
                        aria-pressed={selected}
                        onClick={() =>
                          onProjectChange(project.id, { selectedAngleId: angle.id })
                        }
                      >
                        <span className="workflow-choice-check">
                          {selected ? <Check size={14} /> : null}
                        </span>
                        <span>
                          <strong>{angle.name}</strong>
                          <em>{angle.thesis}</em>
                          <small>为什么成立：{angle.reason}</small>
                          {angle.evidence?.verified_facts?.length ||
                          angle.supporting_materials?.length ? (
                            <small>
                              已确认事实：
                              {(angle.evidence?.verified_facts?.length
                                ? angle.evidence.verified_facts
                                : angle.supporting_materials || []
                              ).join("；")}
                            </small>
                          ) : null}
                          {angle.evidence?.opinions?.length ? (
                            <small>
                              观点 / 舆论（不等于事实）：
                              {angle.evidence.opinions.join("；")}
                            </small>
                          ) : null}
                          {angle.evidence?.examples?.length ? (
                            <small>
                              可用案例：{angle.evidence.examples.join("；")}
                            </small>
                          ) : null}
                          {angle.missing_materials?.length ||
                          angle.required_facts.length ? (
                            <small>
                              还缺材料：
                              {(angle.evidence?.missing_evidence?.length
                                ? angle.evidence.missing_evidence
                                : angle.missing_materials?.length
                                  ? angle.missing_materials
                                  : angle.required_facts
                              ).join("；")}
                            </small>
                          ) : null}
                          {angle.overlap_risk ? (
                            <small>撞题风险：{angle.overlap_risk}</small>
                          ) : null}
                          {angle.main_risks?.length || angle.risk_notes.length ? (
                            <small>
                              主要风险：
                              {(angle.main_risks?.length
                                ? angle.main_risks
                                : angle.risk_notes
                              ).join("；")}
                            </small>
                          ) : null}
                        </span>
                      </button>
                    )
                  })}
                </div>
              ) : (
                <div className="workflow-warning">
                  <CircleAlert size={15} />
                  <div>
                    <strong>没有推荐角度</strong>
                    <span>可以切换到“我来定义”，自己写清楚这条内容要讲什么。</span>
                  </div>
                </div>
              )
            ) : null}
            {project.angleMode === "custom" ? (
              <label className="writing-topic-field">
                <span>我的写作角度</span>
                <textarea
                  aria-label="我的写作角度"
                  value={project.customAngle}
                  onChange={(event) =>
                    onProjectChange(project.id, { customAngle: event.target.value })
                  }
                  placeholder="写清楚你真正想讨论的判断、立场或问题。"
                />
              </label>
            ) : null}
            <StepFooter
              onBack={goBack}
              nextLabel="确认角度"
              onNext={confirmAngle}
            />
          </div>
        ) : null}

        {project.step === "material" ? (
          <div className="writing-panel">
            <div className="workflow-outline-head">
              <div>
                <span>围绕已选角度做第二轮定向研究</span>
                <strong>{selectedAngle || "尚未确认角度"}</strong>
              </div>
              <Badge
                tone={
                  project.materialStatus === "done"
                    ? "success"
                    : project.materialStatus === "running"
                      ? "accent"
                      : "neutral"
                }
              >
                {project.materialStatus === "done"
                  ? `${materialCards.length} 张素材卡`
                  : project.materialStatus === "running"
                    ? "研究中"
                    : "未开始"}
              </Badge>
            </div>
            <p className="workflow-summary">
              第二轮研究和第一轮不同：只找能支撑「已选角度」的具体材料。搜索方向来自选题 +
              已选角度 + 研究简报 + 角度当前缺失的证据，不会重复第一轮的事件综述。
            </p>

            {project.materialStatus === "idle" ? (
              <div className="workflow-actions">
                <span>已有材料也可以先跳过，直接用补充笔记继续。</span>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => void runMaterialResearch()}
                >
                  <Search size={16} />
                  开始定向素材研究
                </button>
              </div>
            ) : null}

            {project.materialStatus === "running" ? (
              <div className="workflow-task-line" role="status">
                <LoaderCircle className="spin" size={15} />
                正在围绕「{selectedAngle.slice(0, 24)}」检索并打开公开来源
              </div>
            ) : null}

            {project.materialStatus === "error" ? (
              <div className="workflow-warning">
                <CircleAlert size={15} />
                <div>
                  <strong>定向素材研究未完成</strong>
                  <span>{project.materialError}</span>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => void runMaterialResearch()}
                  >
                    重试
                  </button>
                </div>
              </div>
            ) : null}

            {project.materialStatus === "done" ? (
              <>
                <div className="workflow-meta-list">
                  <span>共 {materialCards.length} 张素材卡</span>
                  <span>已选 {selection.selected} 条</span>
                  <span>事实类已核实 {selection.verifiedFacts} 条</span>
                  {selection.opinions ? (
                    <span>观点类 {selection.opinions} 条（不等于事实）</span>
                  ) : null}
                  {selection.uncertain ? (
                    <span className="is-warning">
                      待核实 {selection.uncertain} 条
                    </span>
                  ) : null}
                  {project.materialModel ? (
                    <span>研究通道：{project.materialModel}</span>
                  ) : null}
                </div>
                {project.materialStopReason ? (
                  <p className="workflow-summary">
                    停止搜索的理由：{project.materialStopReason}
                  </p>
                ) : null}
                <div className="workflow-actions">
                  <span />
                  <div>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => selectAllMaterials(true)}
                    >
                      全选
                    </button>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => selectAllMaterials(false)}
                    >
                      取消全选
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void runMaterialResearch()}
                    >
                      重新研究
                    </button>
                  </div>
                </div>

                {materialCards.length ? (
                  <div className="material-card-list">
                    {materialCards.map((card) => {
                      const selected = project.selectedMaterialKeys.includes(
                        card.id,
                      )
                      const status = verificationLabel(card)
                      return (
                        <article
                          key={card.id}
                          className={`material-card ${selected ? "is-selected" : ""}`}
                        >
                          <header>
                            <div className="material-card-tags">
                              <Badge tone="neutral">
                                {materialTypeLabels[card.type] || card.type}
                              </Badge>
                              <Badge tone={status.tone}>{status.text}</Badge>
                            </div>
                            <button
                              type="button"
                              className={
                                selected
                                  ? "primary-button material-toggle"
                                  : "secondary-button material-toggle"
                              }
                              aria-pressed={selected}
                              onClick={() => toggleMaterialCard(card.id)}
                            >
                              {selected ? <Check size={14} /> : null}
                              {selected ? "已使用" : "使用这条"}
                            </button>
                          </header>
                          <h4>{card.title}</h4>
                          {card.summary && card.summary !== card.content ? (
                            <p className="material-card-summary">{card.summary}</p>
                          ) : null}
                          <p className="material-card-content">{card.content}</p>
                          <dl className="material-card-meta">
                            <div>
                              <dt>为什么对这个角度有用</dt>
                              <dd>
                                {card.relevance_to_angle || "未说明"}
                              </dd>
                            </div>
                            <div>
                              <dt>建议用途</dt>
                              <dd>{card.suggested_usage || "未指定"}</dd>
                            </div>
                            {card.risk ? (
                              <div>
                                <dt>风险提示</dt>
                                <dd>{card.risk}</dd>
                              </div>
                            ) : null}
                          </dl>
                          <footer>
                            {card.source_url ? (
                              <a
                                href={card.source_url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {card.publisher || card.source || "来源"}
                                {card.published_at
                                  ? ` · ${card.published_at}`
                                  : ""}
                                {" ↗"}
                              </a>
                            ) : (
                              <span className="material-card-nosource">
                                {card.source
                                  ? `${card.source}（无可访问链接）`
                                  : "没有可追溯来源"}
                              </span>
                            )}
                          </footer>
                        </article>
                      )
                    })}
                  </div>
                ) : (
                  <div className="workflow-warning">
                    <CircleAlert size={15} />
                    <div>
                      <strong>这一轮没有取得可用素材</strong>
                      <span>
                        可以补充素材笔记后继续；也可以回到角度步骤换一个角度再研究。
                      </span>
                    </div>
                  </div>
                )}

                {selection.selected === 0 ? (
                  <div className="workflow-warning">
                    <CircleAlert size={15} />
                    <div>
                      <strong>当前没有选择支撑材料，继续写作可能主要依赖通用推理。</strong>
                      <span>
                        至少勾选几条你打算真正用到的材料，结构推荐会更贴合你的稿件。
                      </span>
                    </div>
                  </div>
                ) : null}
              </>
            ) : null}

            {materials.length && project.materialStatus === "idle" ? (
              <>
                <p className="workflow-summary">
                  第一轮研究简报里还有以下信息可以直接作为素材：
                </p>
                <div className="workflow-meta-list">
                  {materials.slice(0, 6).map((item) => (
                    <span key={item.key}>
                      {item.group}：{item.text.slice(0, 40)}
                    </span>
                  ))}
                </div>
              </>
            ) : null}

            <label className="writing-topic-field">
              <span>补充素材 / 素材笔记</span>
              <textarea
                aria-label="补充素材"
                value={project.materialNotes}
                onChange={(event) =>
                  onProjectChange(project.id, {
                    materialNotes: event.target.value,
                  })
                }
                placeholder="记录你打算使用的材料、来源链接或拍摄画面。"
              />
            </label>
            <StepFooter
              onBack={goBack}
              nextLabel="确认素材"
              onNext={goNext}
            />
          </div>
        ) : null}

        {project.step === "structure" ? (
          <div className="writing-panel">
            <p className="workflow-summary">
              结构决定「怎么组织内容」。推荐依据是 选题 + 已选角度 + 已选素材，
              不是只看选题。匹配不到现成结构时，通用结构始终可以继续。
            </p>
            <div className="workflow-meta-list">
              <span>已选角度</span>
              <span>已选素材 {selection.selected} 条</span>
              {selection.verifiedFacts ? (
                <span>事实类已核实 {selection.verifiedFacts} 条</span>
              ) : null}
              {selection.uncertain ? (
                <span className="is-warning">
                  其中待核实 {selection.uncertain} 条
                </span>
              ) : null}
            </div>

            {project.structureStatus === "loading" ? (
              <div className="workflow-task-line" role="status">
                <LoaderCircle className="spin" size={15} />
                正在按已选角度与素材推荐结构
              </div>
            ) : null}

            {project.structureStatus === "error" ? (
              <div className="workflow-warning">
                <CircleAlert size={15} />
                <div>
                  <strong>结构推荐失败，已保留通用结构</strong>
                  <span>{project.structureError}</span>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() => {
                      structureFetchKeyRef.current = ""
                      onProjectChange(project.id, {
                        structureStatus: "idle",
                        structureError: null,
                      })
                    }}
                  >
                    重新推荐
                  </button>
                </div>
              </div>
            ) : null}

            {project.structureStatus === "done" && project.structureNote ? (
              <p className="workflow-summary">{project.structureNote}</p>
            ) : null}

            {selection.selected === 0 ? (
              <div className="workflow-warning">
                <CircleAlert size={15} />
                <div>
                  <strong>还没有选择任何素材</strong>
                  <span>
                    结构仍然可用，但「材料如何填进结构」只能是占位说明；
                    回到素材步骤勾选后，推荐会重新计算。
                  </span>
                </div>
              </div>
            ) : null}

            <div className="structure-list">
              {structureOptions.map((item) => {
                const selected = project.selectedStructureId === item.id
                const isGeneric = item.kind === "generic"
                return (
                  <article
                    key={item.id}
                    className={`structure-card ${selected ? "is-selected" : ""}`}
                  >
                    <header>
                      <div>
                        <strong>
                          {item.name}
                          {isGeneric ? "（无匹配时可用）" : ""}
                        </strong>
                        <small>推进骨架：{item.skeleton.join(" → ")}</small>
                      </div>
                      <button
                        type="button"
                        className={
                          selected
                            ? "primary-button material-toggle"
                            : "secondary-button material-toggle"
                        }
                        aria-pressed={selected}
                        onClick={() => {
                          structureFetchKeyRef.current = ""
                          onProjectChange(project.id, {
                            selectedStructureId: item.id,
                            structureMode: isGeneric ? "generic" : "recommended",
                          })
                        }}
                      >
                        {selected ? <Check size={14} /> : null}
                        {selected ? "已选择" : "选择这个结构"}
                      </button>
                    </header>
                    <dl className="material-card-meta">
                      <div>
                        <dt>为什么适合这个角度</dt>
                        <dd>{item.why_fits || "未说明"}</dd>
                      </div>
                      <div>
                        <dt>已选素材如何填进结构</dt>
                        <dd>
                          {item.material_mapping.length ? (
                            <ul className="structure-mapping">
                              {item.material_mapping.map((mapping) => (
                                <li key={`${item.id}-${mapping.step}`}>
                                  <b>{mapping.step}</b>：
                                  {mapping.material_ids.length
                                    ? mapping.material_ids
                                        .map((materialId) => {
                                          const card = materialCards.find(
                                            (candidate) =>
                                              candidate.id === materialId,
                                          )
                                          return card
                                            ? card.title.slice(0, 24)
                                            : materialId
                                        })
                                        .join("、")
                                    : "暂无对应素材"}
                                  {mapping.note ? `（${mapping.note}）` : ""}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            "未提供映射说明"
                          )}
                        </dd>
                      </div>
                      {item.material_gaps.length ? (
                        <div>
                          <dt>可能材料不足的地方</dt>
                          <dd>{item.material_gaps.join("；")}</dd>
                        </div>
                      ) : null}
                      {item.risk_notes.length ? (
                        <div>
                          <dt>使用注意</dt>
                          <dd>{item.risk_notes.join("；")}</dd>
                        </div>
                      ) : null}
                    </dl>
                  </article>
                )
              })}
            </div>

            {templates.length ? (
              <details className="structure-manual">
                <summary>从结构库手动选择（{templates.length} 个）</summary>
                <div className="workflow-meta-list">
                  {templates.slice(0, 12).map((template) => (
                    <span key={template.id}>
                      {template.name}：{template.skeleton.join(" → ")}
                    </span>
                  ))}
                </div>
                <p className="workflow-summary">
                  手动选择会直接使用该结构的骨架；如需系统按角度和素材重新说明填法，
                  请使用上方的推荐结果。
                </p>
                <button
                  type="button"
                  className="text-button"
                  onClick={onOpenStructures}
                >
                  打开结构库
                </button>
              </details>
            ) : (
              <div className="workflow-warning">
                <CircleAlert size={15} />
                <div>
                  <strong>结构库还是空的</strong>
                  <span>
                    不影响写稿：已提供通用写作结构，选它即可继续下一步。
                  </span>
                </div>
              </div>
            )}

            <StepFooter
              onBack={goBack}
              nextLabel="确认结构"
              onNext={goNext}
            />
          </div>
        ) : null}

        {project.step === "draft" ? (
          <div className="writing-panel">
            <div className="workflow-outline-head">
              <div>
                <span>已选角度（本篇唯一主线）</span>
                <strong>{selectedAngle || "尚未确认角度"}</strong>
              </div>
              <Badge tone="accent">{structureName}</Badge>
            </div>
            <div className="workflow-meta-list">
              <span>
                已选素材 {selection.selected}/{materialCards.length} 条
              </span>
              {selection.verifiedFacts ? (
                <span>事实类已核实 {selection.verifiedFacts} 条</span>
              ) : null}
              {selection.opinions ? (
                <span>观点类 {selection.opinions} 条（不等于事实）</span>
              ) : null}
              {selection.uncertain ? (
                <span className="is-warning">
                  待核实 {selection.uncertain} 条
                </span>
              ) : null}
            </div>

            {project.draftStatus === "idle" || project.draftStatus === "error" ? (
              <>
                <p className="workflow-summary">
                  生成设置只作参考，全部有默认值，不修改也可以直接生成。
                  正文中的事实性内容只允许来自你选的素材、用户输入和已核验事实。
                </p>
                <div className="workflow-form-grid generation-settings">
                  <label>
                    账号类型
                    <select
                      aria-label="账号类型"
                      value={project.settings.accountType}
                      onChange={(event) =>
                        onProjectChange(project.id, {
                          settings: {
                            ...project.settings,
                            accountType: event.target.value,
                          },
                        })
                      }
                    >
                      <option>娱乐吃瓜号</option>
                      <option>泛娱乐观点号</option>
                      <option>商业分析号</option>
                      <option>社会观察号</option>
                    </select>
                  </label>
                  <label>
                    参考时长
                    <select
                      aria-label="参考时长"
                      value={project.settings.durationSeconds}
                      onChange={(event) =>
                        onProjectChange(project.id, {
                          settings: {
                            ...project.settings,
                            durationSeconds: Number(event.target.value),
                          },
                        })
                      }
                    >
                      <option value={30}>30 秒</option>
                      <option value={45}>45 秒</option>
                      <option value={60}>60 秒</option>
                      <option value={90}>90 秒</option>
                    </select>
                  </label>
                  <label>
                    语气
                    <input
                      aria-label="语气"
                      value={project.settings.tone}
                      onChange={(event) =>
                        onProjectChange(project.id, {
                          settings: {
                            ...project.settings,
                            tone: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                  <label>
                    传播目标
                    <input
                      aria-label="传播目标"
                      value={project.settings.goal}
                      onChange={(event) =>
                        onProjectChange(project.id, {
                          settings: {
                            ...project.settings,
                            goal: event.target.value,
                          },
                        })
                      }
                    />
                  </label>
                </div>
                {project.draftStatus === "error" ? (
                  <div className="workflow-warning">
                    <CircleAlert size={15} />
                    <div>
                      <strong>初稿生成失败</strong>
                      <span>{project.draftError}</span>
                    </div>
                  </div>
                ) : null}
                <div className="workflow-actions">
                  <span>
                    只会生成一篇主稿；材料不足的部分不会写进正文，而是记在下方缺口里。
                  </span>
                  <button
                    type="button"
                    className="primary-button"
                    onClick={() => void runDraftGeneration()}
                  >
                    <Sparkles size={16} />
                    生成完整初稿
                  </button>
                </div>
              </>
            ) : null}

            {project.draftStatus === "running" ? (
              <div className="workflow-task-line" role="status">
                <LoaderCircle className="spin" size={15} />
                正在按已选结构与素材生成完整初稿（约 1-3 分钟）
              </div>
            ) : null}

            {project.draftStatus === "done" ? (
              <>
                {project.draftGenerationNote ? (
                  <p className="workflow-summary">{project.draftGenerationNote}</p>
                ) : null}
                <div className="workflow-meta-list">
                  <span>正文 {speechCharacterCount(project.draftText)} 字</span>
                  <span>
                    预计 {estimatedSpeechSeconds(project.draftText)} 秒 / 参考{" "}
                    {project.settings.durationSeconds} 秒
                  </span>
                  <span
                    className={
                      speechLengthStatus(
                        project.draftText,
                        project.settings.durationSeconds,
                      ).status === "ready"
                        ? ""
                        : "is-warning"
                    }
                  >
                    {lengthHint}
                  </span>
                  {project.draftModel ? (
                    <span>生成通道：{project.draftModel}</span>
                  ) : null}
                </div>

                <label className="writing-topic-field">
                  <span>标题</span>
                  <input
                    aria-label="标题"
                    value={project.draftTitle}
                    onChange={(event) =>
                      onProjectChange(project.id, {
                        draftTitle: event.target.value,
                      })
                    }
                  />
                </label>
                {project.titleCandidates.length ? (
                  <div className="title-candidate-row">
                    <small>标题候选：</small>
                    {project.titleCandidates.map((candidate) => (
                      <button
                        type="button"
                        key={candidate}
                        className="text-button"
                        onClick={() =>
                          onProjectChange(project.id, { draftTitle: candidate })
                        }
                      >
                        {candidate}
                      </button>
                    ))}
                  </div>
                ) : null}

                <label className="writing-topic-field">
                  <span>完整口播稿（可直接编辑）</span>
                  <textarea
                    aria-label="完整口播稿"
                    className="draft-editor"
                    value={project.draftText}
                    onChange={(event) =>
                      onProjectChange(project.id, {
                        draftText: event.target.value,
                      })
                    }
                  />
                </label>

                <div className="workflow-actions">
                  <div className="draft-version-list">
                    {project.draftVersions.map((version) => (
                      <button
                        type="button"
                        key={version.id}
                        className="text-button"
                        onClick={() => restoreDraftVersion(version.id)}
                      >
                        {version.label}（
                        {new Date(version.savedAt).toLocaleTimeString()}）
                      </button>
                    ))}
                  </div>
                  <div>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={saveDraftVersion}
                    >
                      保存版本
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => void runDraftGeneration()}
                    >
                      重新生成
                    </button>
                    <button
                      type="button"
                      className="primary-button"
                      onClick={goNext}
                    >
                      进入审稿
                      <ArrowRight size={15} />
                    </button>
                  </div>
                </div>

                {project.evidenceCheck ? (
                  <details className="structure-manual" open={!project.evidenceCheck.passed}>
                    <summary>
                      证据检查：
                      {project.evidenceCheck.passed
                        ? "未发现无依据事实"
                        : `已处理 ${project.evidenceCheck.unsupported_claims.length} 条无依据陈述`}
                    </summary>
                    {project.evidenceCheck.notes.length ? (
                      <div className="workflow-meta-list">
                        {project.evidenceCheck.notes.map((note) => (
                          <span key={note}>{note}</span>
                        ))}
                      </div>
                    ) : null}
                    {project.evidenceCheck.unsupported_claims.length ? (
                      <div className="workflow-warning">
                        <CircleAlert size={15} />
                        <div>
                          <strong>以下陈述缺少证据，已处理（不会留在正文里）</strong>
                          {project.evidenceCheck.unsupported_claims.map((claim) => (
                            <span key={claim.text}>
                              {claim.text}（{claim.reason}｜处理：
                              {claim.action === "removed"
                                ? "已删除"
                                : claim.action === "downgraded"
                                  ? "已降级表达"
                                  : "已改为观点"}
                              ）
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null}
                    {project.usedMaterialIds.length ||
                    project.usedClaimIds.length ? (
                      <p className="workflow-summary">
                        本篇使用素材：{project.usedMaterialIds.join("、") || "无"}
                        ；使用已核验事实：
                        {project.usedClaimIds.join("、") || "无"}
                      </p>
                    ) : null}
                    {project.evidenceMap.length ? (
                      <ul className="evidence-map">
                        {project.evidenceMap.map((item) => (
                          <li key={`${item.section}-${item.note}`}>
                            <b>{item.section}</b>
                            {" ← 素材 "}
                            {item.material_ids.length
                              ? item.material_ids.join("、")
                              : "无"}
                            {item.claim_ids.length
                              ? `；事实 ${item.claim_ids.join("、")}`
                              : ""}
                            {item.note ? `（${item.note}）` : ""}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </details>
                ) : null}

                {project.materialGaps.length ? (
                  <details className="structure-manual">
                    <summary>
                      材料缺口（正文之外）：{project.materialGaps.length} 条
                    </summary>
                    <ul className="material-gap-list">
                      {project.materialGaps.map((item) => (
                        <li key={item.gap}>
                          <b>缺口：</b>
                          {item.gap}
                          <br />
                          <b>处理：</b>
                          {item.handling}
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}

                {project.structureCoverage.length ? (
                  <details className="structure-manual">
                    <summary>结构执行情况</summary>
                    <ul className="evidence-map">
                      {project.structureCoverage.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                  </details>
                ) : null}

                {project.shotSuggestions.length ||
                project.subtitleRhythm.length ||
                project.commentCta ? (
                  <details className="structure-manual">
                    <summary>分镜 / 字幕 / 互动建议</summary>
                    <div className="workflow-meta-list">
                      {project.shotSuggestions.map((item) => (
                        <span key={item}>分镜：{item}</span>
                      ))}
                      {project.subtitleRhythm.map((item) => (
                        <span key={item}>字幕：{item}</span>
                      ))}
                      {project.commentCta ? (
                        <span>互动：{project.commentCta}</span>
                      ) : null}
                    </div>
                  </details>
                ) : null}

                <div className="workflow-warning">
                  <CircleAlert size={15} />
                  <div>
                    <strong>风险检查（Draft Risk）</strong>
                    <span>
                      等级：{riskLevelLabel(project.evidenceCheck)}
                      {project.evidenceCheck?.passed === false
                        ? "；请在审稿步骤确认证据检查项。"
                        : "；未发现高敏或攻击性表达。"}
                    </span>
                  </div>
                </div>
              </>
            ) : null}
          </div>
        ) : null}

        {project.step === "review" ? (
          <div className="writing-panel">
            <p className="workflow-summary">
              Phase 5 会接入 AI 痕迹标注（annotation）和分阶段风险审查。
              当前先做基础人工检查，检查结果会随稿件一起导出。
            </p>
            <div className="workflow-choice-list">
              {project.reviewChecks.map((check) => (
                <button
                  type="button"
                  key={check.id}
                  className={`workflow-choice ${check.checked ? "is-selected" : ""}`}
                  aria-pressed={check.checked}
                  onClick={() => toggleReviewCheck(check.id)}
                >
                  <span className="workflow-choice-check">
                    {check.checked ? <Check size={14} /> : null}
                  </span>
                  <span>
                    <strong>{check.label}</strong>
                  </span>
                </button>
              ))}
            </div>
            {brief?.risk_flags.length ? (
              <div className="workflow-warning">
                <CircleAlert size={15} />
                <div>
                  <strong>研究阶段记录的风险</strong>
                  {brief.risk_flags.map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </div>
              </div>
            ) : null}
            <label className="writing-topic-field">
              <span>审稿备注</span>
              <textarea
                aria-label="审稿备注"
                value={project.reviewNotes}
                onChange={(event) =>
                  onProjectChange(project.id, { reviewNotes: event.target.value })
                }
                placeholder="记录需要修改的表达、待确认的事实或客户反馈。"
              />
            </label>
            <StepFooter onBack={goBack} nextLabel="进入导出" onNext={goNext} />
          </div>
        ) : null}

        {project.step === "export" ? (
          <div className="writing-panel">
            <div className="workflow-draft-meta">
              <span>选题 {project.topic.slice(0, 16)}</span>
              <span>{selectedAngle ? "已选角度" : "未设定角度"}</span>
              <span>{structureName}</span>
              <span>成稿 {project.draftText.replace(/\s+/g, "").length} 字</span>
            </div>
            <p className="workflow-summary">
              导出内容包含选题、研究简报、角度、已选素材、写作结构、成稿和审稿记录。
              审稿勾选项会作为清单写入 Markdown。
            </p>
            <div className="workflow-actions">
              <button type="button" className="secondary-button" onClick={onNewProject}>
                <Plus size={15} />
                新建另一篇
              </button>
              <div>
                <button type="button" className="text-button" onClick={() => void copyMarkdown()}>
                  <Copy size={14} />
                  复制 Markdown
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() =>
                    downloadFile(
                      `${safeFilename}.md`,
                      exportMarkdown(),
                      "text/markdown;charset=utf-8",
                    )
                  }
                >
                  <Download size={15} />
                  Markdown
                </button>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() =>
                    downloadFile(
                      `${safeFilename}.json`,
                      JSON.stringify(
                        buildWritingProjectExport(
                          project,
                          structureName,
                          structureSkeleton,
                          selectedAngle,
                          selectedMaterialTexts,
                        ),
                        null,
                        2,
                      ),
                      "application/json;charset=utf-8",
                    )
                  }
                >
                  <Download size={15} />
                  导出 JSON
                </button>
              </div>
            </div>
            {project.exportedAt ? (
              <p className="workflow-summary">
                最近一次导出：{new Date(project.exportedAt).toLocaleString()}
              </p>
            ) : null}
          </div>
        ) : null}

        {project.step !== "topic" &&
        project.step !== "research" &&
        project.step !== "export" ? (
          <p className="writing-project-footnote">
            每一步都可以返回修改；状态保存在当前会话中（当前阶段不做数据库持久化）。
          </p>
        ) : null}
      </Card>
    </div>
  )
}
