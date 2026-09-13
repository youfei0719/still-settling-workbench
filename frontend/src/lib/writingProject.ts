import type {
  WritingProjectReviewCheck,
  WritingProjectState,
  WritingProjectStep,
} from "@/types/workbench"

/**
 * Phase 1：WritingProject 只存在于前端内存（由 App 持有）。
 * 这里集中步骤顺序、默认值和导出辅助，避免组件里散落流程常量。
 */

export const writingProjectSteps: Array<{
  id: WritingProjectStep
  label: string
}> = [
  { id: "topic", label: "选题" },
  { id: "research", label: "研究" },
  { id: "angle", label: "角度" },
  { id: "material", label: "素材" },
  { id: "structure", label: "结构" },
  { id: "draft", label: "成稿" },
  { id: "review", label: "审稿" },
  { id: "export", label: "导出" },
]

export function writingProjectStepLabel(step: WritingProjectStep) {
  return writingProjectSteps.find((item) => item.id === step)?.label || step
}

export function writingProjectStepIndex(step: WritingProjectStep) {
  return writingProjectSteps.findIndex((item) => item.id === step)
}

export function defaultReviewChecks(): WritingProjectReviewCheck[] {
  return [
    { id: "fact", label: "事实与来源已核对", checked: false },
    { id: "safety", label: "隐私 / 人身攻击 / 未成年人风险已检查", checked: false },
    { id: "platform", label: "平台规则与客户禁用表达已规避", checked: false },
    { id: "tone", label: "口播语气已通读，没有模型腔和空话", checked: false },
  ]
}

export function createWritingProject(
  topic: string,
  supplement: string,
): WritingProjectState {
  const now = new Date().toISOString()
  return {
    id: `writing-project-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`,
    topic: topic.trim(),
    supplement: supplement.trim(),
    createdAt: now,
    updatedAt: now,
    step: "topic",
    researchStatus: "idle",
    researchError: null,
    research: null,
    angleMode: "recommended",
    selectedAngleId: "",
    customAngle: "",
    materialStatus: "idle",
    materialError: null,
    materialCards: [],
    materialStopReason: "",
    materialGuidance: "",
    materialModel: null,
    selectedMaterialKeys: [],
    materialNotes: "",
    structureMode: "generic",
    selectedStructureId: "",
    structureRecommendations: [],
    structureGeneric: null,
    structureNote: "",
    structureStatus: "idle",
    structureError: null,
    settings: {
      accountType: "娱乐吃瓜号",
      durationSeconds: 60,
      tone: "真人口语",
      goal: "引发讨论",
    },
    draftTitle: "",
    draftText: "",
    draftStatus: "idle",
    draftError: null,
    draftGenerationNote: "",
    draftModel: null,
    titleCandidates: [],
    shotSuggestions: [],
    subtitleRhythm: [],
    commentCta: "",
    usedMaterialIds: [],
    usedClaimIds: [],
    materialGaps: [],
    evidenceMap: [],
    evidenceCheck: null,
    structureCoverage: [],
    draftVersions: [],
    reviewNotes: "",
    reviewChecks: defaultReviewChecks(),
    exportedAt: null,
  }
}

/** 已选素材（SelectedMaterials）：只有这些能进入结构推荐与成稿。 */
export function selectedMaterialCards(project: WritingProjectState) {
  return project.materialCards.filter((item) =>
    project.selectedMaterialKeys.includes(item.id),
  )
}

/**
 * 发送给后端时，把选中标记写进卡片本身。
 * 前端用 selectedMaterialKeys 作为唯一真源，卡片上的 selected 字段可能仍是旧值，
 * 若不显式同步，后端会把“已选素材”当成未选而拒绝使用。
 */
export function selectedMaterialCardsForRequest(project: WritingProjectState) {
  return selectedMaterialCards(project).map((item) => ({
    ...item,
    selected: true,
  }))
}

export interface MaterialSelectionSummary {
  total: number
  selected: number
  /** 事实类素材（fact / data / case / comparison / background）中来源已核实的条数。 */
  verifiedFacts: number
  /** 观点类素材（opinion / quote）：可追溯来源，但不等于事实。 */
  opinions: number
  uncertain: number
}

const opinionMaterialTypes = new Set(["opinion", "quote"])

export function isOpinionMaterial(type: string) {
  return opinionMaterialTypes.has(type)
}

export function materialSelectionSummary(
  project: WritingProjectState,
): MaterialSelectionSummary {
  const selected = selectedMaterialCards(project)
  return {
    total: project.materialCards.length,
    selected: selected.length,
    verifiedFacts: selected.filter(
      (item) =>
        item.verification_status === "verified" && !isOpinionMaterial(item.type),
    ).length,
    opinions: selected.filter((item) => isOpinionMaterial(item.type)).length,
    uncertain: selected.filter((item) => item.verification_status !== "verified")
      .length,
  }
}

/**
 * SelectedAngle 是强制决策节点：进入素材 / 结构 / 成稿 / 审稿 / 导出前必须存在。
 * 只承认两条合法路径：选择推荐角度，或用户自定义角度。
 */
export function selectedAngleText(project: WritingProjectState): string {
  if (project.angleMode === "custom") return project.customAngle.trim()
  const angles = project.research?.angle_candidates || []
  return (
    angles.find((item) => item.id === project.selectedAngleId)?.thesis.trim() || ""
  )
}

export function hasSelectedAngle(project: WritingProjectState): boolean {
  if (project.angleMode === "custom") return project.customAngle.trim().length >= 6
  return Boolean(project.selectedAngleId.trim())
}

/** 需要 SelectedAngle 作为前置的步骤。 */
export const angleRequiredSteps: WritingProjectStep[] = [
  "material",
  "structure",
  "draft",
  "review",
  "export",
]

export function isWritingProjectState(
  value: unknown,
): value is WritingProjectState {
  if (!value || typeof value !== "object") return false
  const candidate = value as Partial<WritingProjectState>
  return (
    typeof candidate.id === "string" &&
    typeof candidate.topic === "string" &&
    typeof candidate.step === "string"
  )
}

/**
 * 第一轮研究简报里的候选材料（兼容视图）。
 * Phase 3 起，素材步骤默认使用第二轮定向研究产出的 MaterialCard。
 */
export function candidateMaterials(project: WritingProjectState) {
  const brief = project.research?.research_brief
  if (!brief) return []
  const verified = brief.verification_status === "verified"
  const groups: Array<{ items: string[]; label: string }> = [
    { items: brief.verified_facts, label: verified ? "已确认事实" : "事实候选" },
    { items: brief.concrete_details || [], label: "用户提供的信息" },
    { items: brief.timeline || [], label: "时间线" },
  ]
  const seen = new Set<string>()
  const items: Array<{ key: string; text: string; group: string }> = []
  for (const group of groups) {
    for (const item of group.items) {
      const text = (item || "").trim()
      if (!text || seen.has(text)) continue
      seen.add(text)
      items.push({ key: text, text, group: group.label })
    }
  }
  return items
}

export interface WritingProjectExportPayload {
  topic: string
  research: {
    status: WritingProjectState["researchStatus"]
    summary: string
    verifiedFacts: string[]
    uncertainClaims: string[]
    sources: Array<{ title: string; url: string; publisher?: string }>
  }
  angle: string
  materials: string[]
  structure: { mode: string; name: string; skeleton: string[] }
  draft: { title: string; text: string }
  review: { notes: string; checks: WritingProjectReviewCheck[] }
}

export function buildWritingProjectExport(
  project: WritingProjectState,
  structureName: string,
  structureSkeleton: string[],
  selectedAngle: string,
  selectedMaterials: string[],
): WritingProjectExportPayload {
  const brief = project.research?.research_brief
  return {
    topic: project.topic,
    research: {
      status: project.researchStatus,
      summary:
        brief?.summary ||
        brief?.research_gap?.[0] ||
        (brief?.verified_facts?.length
          ? "已从用户提供材料中整理出可核实事实。"
          : "研究简报尚未生成。"),
      verifiedFacts: brief?.verified_facts || [],
      uncertainClaims: [
        ...(brief?.uncertain_claims || []),
        ...(brief?.research_gap || []),
      ],
      sources: (brief?.sources || []).map((source) => ({
        title: source.title,
        url: source.url,
        publisher: source.publisher,
      })),
    },
    angle: selectedAngle,
    materials: selectedMaterials,
    structure: {
      mode: project.structureMode,
      name: structureName,
      skeleton: structureSkeleton,
    },
    draft: { title: project.draftTitle, text: project.draftText },
    review: { notes: project.reviewNotes, checks: project.reviewChecks },
  }
}

export function buildWritingProjectMarkdown(
  project: WritingProjectState,
  structureName: string,
  structureSkeleton: string[],
  selectedAngle: string,
  selectedMaterials: string[],
): string {
  const payload = buildWritingProjectExport(
    project,
    structureName,
    structureSkeleton,
    selectedAngle,
    selectedMaterials,
  )
  const lines: string[] = []
  lines.push(`# ${payload.draft.title || payload.topic}`)
  lines.push("")
  lines.push("## 选题")
  lines.push(payload.topic)
  lines.push("")
  lines.push("## 研究简报")
  lines.push(`- 状态：${payload.research.status}`)
  lines.push(`- 摘要：${payload.research.summary}`)
  if (payload.research.verifiedFacts.length) {
    lines.push("- 已确认事实：")
    for (const fact of payload.research.verifiedFacts) lines.push(`  - ${fact}`)
  }
  if (payload.research.uncertainClaims.length) {
    lines.push("- 存疑 / 待核实：")
    for (const item of payload.research.uncertainClaims) lines.push(`  - ${item}`)
  }
  if (payload.research.sources.length) {
    lines.push("- 来源：")
    for (const source of payload.research.sources) {
      lines.push(`  - ${source.title} ${source.url}`)
    }
  }
  lines.push("")
  lines.push("## 角度")
  lines.push(payload.angle || "未设定固定角度")
  lines.push("")
  lines.push("## 已选素材")
  if (payload.materials.length) {
    for (const item of payload.materials) lines.push(`- ${item}`)
  } else {
    lines.push("- 未勾选素材")
  }
  lines.push("")
  lines.push("## 写作结构")
  lines.push(`- ${payload.structure.name}（${payload.structure.mode}）`)
  for (const step of payload.structure.skeleton) lines.push(`- ${step}`)
  lines.push("")
  lines.push("## 成稿")
  lines.push(payload.draft.text || "（尚未成稿）")
  lines.push("")
  lines.push("## 审稿记录")
  for (const check of payload.review.checks) {
    lines.push(`- [${check.checked ? "x" : " "}] ${check.label}`)
  }
  if (payload.review.notes) {
    lines.push("")
    lines.push(payload.review.notes)
  }
  lines.push("")
  return lines.join("\n")
}
