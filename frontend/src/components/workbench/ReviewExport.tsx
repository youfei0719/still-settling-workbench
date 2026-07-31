import {
  Check,
  CheckCircle2,
  Copy,
  Download,
  FileCheck2,
  Link2,
  LoaderCircle,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react"
import {
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import {
  fetchHumanReviewTemplate,
  fetchSelectionRewriteSuggestions,
  runSkillReleaseEvaluation,
  rewriteScriptSelection,
  updateHumanReviewTemplate,
} from "@/api/workbench"
import { formatSpeechParagraphs, speechLengthStatus } from "@/lib/speech"
import type {
  AnalyzeTextResponse,
  DraftRewriteResponse,
  ExternalGateReport,
  FactSource,
  GeneratedScript,
  GeneratedScriptUpdatePayload,
  HumanReviewItem,
  SkillReleaseEvaluationResponse,
  ScriptProductionStatus,
  SelectionRewriteSuggestion,
} from "@/types/workbench"
import { Badge, Card, EmptyState, RiskBadge, SectionHeader } from "./ui"

type ScriptDraft = {
  title: string
  spoken_script: string
  shot_suggestions: string
  subtitle_rhythm: string
  comment_cta: string
  production_status: ScriptProductionStatus
  version_label: string
  editor_note: string
}

type TextSelection = {
  start: number
  end: number
  text: string
  x: number
  y: number
  scope: "draft" | "candidate"
}

const MAX_REWRITE_FACTS = 12

function compactRewriteFacts(items: string[]) {
  const seen = new Set<string>()
  return items
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false
      seen.add(item)
      return true
    })
    .slice(0, MAX_REWRITE_FACTS)
}

const statusLabels: Record<ScriptProductionStatus, string> = {
  draft: "结构待填",
  editing: "精修中",
  review_ready: "待复核",
  exported: "已导出",
}

function draftFromScript(script: GeneratedScript): ScriptDraft {
  return {
    title: script.title,
    spoken_script: formatSpeechParagraphs(script.spoken_script),
    shot_suggestions: script.shot_suggestions.join("\n"),
    subtitle_rhythm: script.subtitle_rhythm.join("\n"),
    comment_cta: script.comment_cta,
    production_status: script.production_status || "draft",
    version_label: script.version_label || "v1",
    editor_note: script.editor_note || "",
  }
}

function splitLines(value: string) {
  return value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean)
}

function hasStructurePlaceholders(value: string) {
  return /【写作结构工作稿】|【段落\s*\d|你来填写|写作建议：|结构骨架：/.test(
    value,
  )
}

function finishChecks(script: GeneratedScript, draft: ScriptDraft) {
  const shots = splitLines(draft.shot_suggestions)
  const subtitles = splitLines(draft.subtitle_rhythm)
  const speech = speechLengthStatus(
    draft.spoken_script,
    script.duration_seconds,
  )
  const stillStructure = hasStructurePlaceholders(draft.spoken_script)
  return [
    {
      key: "title",
      label: "标题",
      passed: draft.title.trim().length >= 4,
      detail:
        draft.title.trim().length >= 4
          ? "已填写"
          : "标题过短，导出前补一个可发布标题",
    },
    {
      key: "spoken",
      label: "口播正文",
      passed: speech.status === "ready" && !stillStructure,
      detail: stillStructure
        ? "仍是结构工作稿，请把提示替换成完整口播正文"
        : speech.status === "ready"
          ? `${speech.count} 字 · 约 ${speech.estimatedSeconds} 秒，接近 ${script.duration_seconds} 秒创作目标`
          : `${speech.count} 字 · 约 ${speech.estimatedSeconds} 秒，体量明显偏离 ${script.duration_seconds} 秒参考值`,
    },
    {
      key: "shots",
      label: "分镜",
      passed: shots.length > 0,
      detail: shots.length
        ? `${shots.length} 条分镜建议`
        : "至少保留 1 条拍摄/剪辑提示",
    },
    {
      key: "subtitles",
      label: "字幕节奏",
      passed: subtitles.length > 0,
      detail: subtitles.length
        ? `${subtitles.length} 条字幕节奏`
        : "至少保留 1 条字幕节奏",
    },
    {
      key: "risk",
      label: "风险",
      passed: script.risk_check.level !== "high",
      detail:
        script.risk_check.level === "high"
          ? "高风险表达需要先改写"
          : `${script.risk_check.level}，可进入人工复核`,
    },
    {
      key: "human",
      label: "发布流程",
      passed:
        draft.production_status === "review_ready" ||
        draft.production_status === "exported",
      detail:
        draft.production_status === "review_ready" ||
        draft.production_status === "exported"
          ? "已提交人工复核"
          : "精修完成后提交复核",
    },
  ]
}

function gateValue(gate: Record<string, unknown> | undefined, key: string) {
  const value = gate?.[key]
  return typeof value === "string" ? value : ""
}

function gateNumber(gate: Record<string, unknown> | undefined, key: string) {
  const value = gate?.[key]
  return typeof value === "number" ? value : 0
}

function downloadFile(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.style.display = "none"
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

function markdownForScript(script: GeneratedScript) {
  const spokenScript = formatSpeechParagraphs(script.spoken_script)
  return [
    `# ${script.title}`,
    "",
    `> ${script.content_angle} · 参考时长 ${script.duration_seconds} 秒`,
    "",
    "## 口播稿",
    "",
    spokenScript,
    "",
    "## 分镜建议",
    "",
    ...script.shot_suggestions.map((item, index) => `${index + 1}. ${item}`),
    "",
    "## 字幕节奏",
    "",
    ...script.subtitle_rhythm.map((item, index) => `${index + 1}. ${item}`),
    "",
    "## 评论引导",
    "",
    script.comment_cta,
    "",
    script.editor_note ? `\n## 制作备注\n\n${script.editor_note}` : "",
  ]
    .filter(Boolean)
    .join("\n")
}

export function ReviewExport({
  analysis,
  hotspotResult,
  selectedScript,
  generatedScripts,
  onSelectScript,
  onUpdateScript,
  onToast,
  externalGates,
  externalGateLoading,
  onRefreshExternalGates,
  onCreateHumanReviewTemplate,
  showDiagnostics = false,
  onlyDiagnostics = false,
}: {
  analysis: AnalyzeTextResponse | null
  hotspotResult: DraftRewriteResponse | null
  selectedScript: GeneratedScript | null
  generatedScripts: GeneratedScript[]
  onSelectScript: (script: GeneratedScript) => void
  onUpdateScript: (
    scriptId: string,
    payload: GeneratedScriptUpdatePayload,
  ) => Promise<GeneratedScript>
  onToast: (message: string) => void
  externalGates: ExternalGateReport | null
  externalGateLoading: boolean
  onRefreshExternalGates: (options?: {
    runLink?: boolean
    expectModel?: boolean
  }) => Promise<void> | void
  onCreateHumanReviewTemplate: () => Promise<void> | void
  showDiagnostics?: boolean
  onlyDiagnostics?: boolean
}) {
  const initialScript =
    selectedScript ||
    hotspotResult?.scripts[0] ||
    analysis?.generated_preview ||
    null
  const scripts = useMemo(() => {
    const all = [...generatedScripts]
    if (
      initialScript &&
      !all.some((script) => script.id === initialScript.id)
    ) {
      all.unshift(initialScript)
    }
    return all.filter((script, index, list) => {
      const versionKey = `${script.title}\u0000${script.content_angle}\u0000${script.version_label || "v1"}`
      return (
        list.findIndex(
          (item) =>
            `${item.title}\u0000${item.content_angle}\u0000${item.version_label || "v1"}` ===
            versionKey,
        ) === index
      )
    })
  }, [generatedScripts, initialScript])
  const activeScript = selectedScript || scripts[0] || null
  const [draft, setDraft] = useState<ScriptDraft | null>(
    activeScript ? draftFromScript(activeScript) : null,
  )
  const [saving, setSaving] = useState(false)
  const [reviewItems, setReviewItems] = useState<HumanReviewItem[]>([])
  const [reviewLoading, setReviewLoading] = useState(false)
  const [reviewSaving, setReviewSaving] = useState(false)
  const [releaseEvaluation, setReleaseEvaluation] =
    useState<SkillReleaseEvaluationResponse | null>(null)
  const [releaseEvaluationLoading, setReleaseEvaluationLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scriptEditorRef = useRef<HTMLTextAreaElement>(null)
  const rewriteCandidateRef = useRef<HTMLTextAreaElement>(null)
  const selectionActionsRef = useRef<HTMLDivElement>(null)
  const [textSelection, setTextSelection] = useState<TextSelection | null>(null)
  const [sourceSelection, setSourceSelection] = useState<TextSelection | null>(
    null,
  )
  const [selectionComposerOpen, setSelectionComposerOpen] = useState(false)
  const [selectionInstruction, setSelectionInstruction] = useState("")
  const [selectionRewriting, setSelectionRewriting] = useState(false)
  const [selectionReplacement, setSelectionReplacement] = useState("")
  const [selectionChangeSummary, setSelectionChangeSummary] = useState("")
  const [selectionSuggestions, setSelectionSuggestions] = useState<
    SelectionRewriteSuggestion[]
  >([])
  const [selectedSuggestionIds, setSelectedSuggestionIds] = useState<string[]>(
    [],
  )
  const [selectionSuggestionsLoading, setSelectionSuggestionsLoading] =
    useState(false)
  const [selectionSuggestionError, setSelectionSuggestionError] = useState("")
  const [selectionSupportingFacts, setSelectionSupportingFacts] = useState<
    string[]
  >([])
  const [selectionSources, setSelectionSources] = useState<FactSource[]>([])
  const [followupSuggestions, setFollowupSuggestions] = useState<
    SelectionRewriteSuggestion[]
  >([])
  const [followupSuggestionsLoading, setFollowupSuggestionsLoading] =
    useState(false)

  useEffect(() => {
    setDraft(activeScript ? draftFromScript(activeScript) : null)
    setError(null)
    setTextSelection(null)
    setSourceSelection(null)
    setSelectionComposerOpen(false)
    setSelectionInstruction("")
    setSelectionReplacement("")
    setSelectionSuggestions([])
    setSelectedSuggestionIds([])
    setSelectionSupportingFacts([])
    setSelectionSources([])
    setFollowupSuggestions([])
  }, [activeScript?.id, activeScript])

  useEffect(() => {
    if (!selectionReplacement || selectionRewriting) return
    if (window.innerWidth > 760) return
    window.requestAnimationFrame(() => {
      selectionActionsRef.current?.scrollIntoView({
        block: "center",
        inline: "nearest",
      })
    })
  }, [selectionReplacement, selectionRewriting])

  const applyDraft = (updated: Partial<ScriptDraft>) =>
    setDraft((current) => (current ? { ...current, ...updated } : current))
  const applyEditorialDraft = (updated: Partial<ScriptDraft>) =>
    setDraft((current) =>
      current
        ? { ...current, ...updated, production_status: "editing" }
        : current,
    )

  const captureTextSelection = (
    target: HTMLTextAreaElement,
    scope: "draft" | "candidate" = "draft",
    point?: { clientX: number; clientY: number },
  ) => {
    const start = target.selectionStart
    const end = target.selectionEnd
    const text = target.value.slice(start, end)
    if (end - start < 2 || !text.trim()) {
      if (!selectionComposerOpen) setTextSelection(null)
      return
    }
    const rect = target.getBoundingClientRect()
    const x = Math.min(
      window.innerWidth - 132,
      Math.max(132, point?.clientX ?? rect.left + rect.width / 2),
    )
    const y = Math.max(64, (point?.clientY ?? rect.top + 48) - 48)
    setTextSelection({ start, end, text, x, y, scope })
    if (scope === "draft") {
      setSourceSelection(null)
      setSelectionComposerOpen(false)
      setSelectionReplacement("")
      setFollowupSuggestions([])
    }
    setSelectionChangeSummary("")
    setSelectionSuggestions([])
    setSelectedSuggestionIds([])
    setSelectionSuggestionError("")
    setSelectionSupportingFacts([])
    setSelectionSources([])
  }

  const handleSelectionMouseUp = (
    event: ReactMouseEvent<HTMLTextAreaElement>,
  ) => {
    captureTextSelection(event.currentTarget, "draft", event)
  }

  const handleSelectionKeyUp = (
    event: ReactKeyboardEvent<HTMLTextAreaElement>,
  ) => {
    if (
      event.shiftKey ||
      ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)
    ) {
      captureTextSelection(event.currentTarget, "draft")
    }
  }

  const scriptWithCandidate = (candidate: string) => {
    if (!draft || !sourceSelection) return draft?.spoken_script || candidate
    return `${draft.spoken_script.slice(0, sourceSelection.start)}${candidate}${draft.spoken_script.slice(sourceSelection.end)}`
  }

  const loadSelectionSuggestions = async (
    selection: TextSelection,
    fullScript: string,
  ) => {
    if (!activeScript) return
    setSelectionSuggestionsLoading(true)
    setSelectionSuggestionError("")
    try {
      const response = await fetchSelectionRewriteSuggestions({
        selected_text: selection.text,
        full_script: fullScript,
        account_type: activeScript.account_type,
        duration_seconds: activeScript.duration_seconds,
        tone: "保持当前版本语气",
        skill_name: activeScript.template_used,
        verified_facts: compactRewriteFacts([
          ...(hotspotResult?.fact_verification?.verified_facts || []),
          ...selectionSupportingFacts,
        ]),
      })
      setSelectionSuggestions(response.suggestions)
      setSelectedSuggestionIds([])
    } catch (event) {
      setSelectionSuggestionError(
        event instanceof Error
          ? event.message
          : "没有取得动态建议，可直接输入要求。",
      )
    } finally {
      setSelectionSuggestionsLoading(false)
    }
  }

  const openSelectionComposer = async () => {
    if (!activeScript || !draft || !textSelection) return
    const baseSelection =
      textSelection.scope === "draft" ? textSelection : sourceSelection
    if (!baseSelection) return
    if (textSelection.scope === "draft") {
      setSourceSelection(baseSelection)
    }
    setSelectionComposerOpen(true)
    await loadSelectionSuggestions(
      textSelection,
      textSelection.scope === "candidate"
        ? scriptWithCandidate(selectionReplacement)
        : draft.spoken_script,
    )
  }

  const handleCandidateSelection = async (target: HTMLTextAreaElement) => {
    const start = target.selectionStart
    const end = target.selectionEnd
    const text = target.value.slice(start, end)
    if (end - start < 2 || !text.trim()) return
    const selection: TextSelection = {
      start,
      end,
      text,
      x: 0,
      y: 0,
      scope: "candidate",
    }
    setTextSelection(selection)
    setSelectionInstruction("")
    setFollowupSuggestions([])
    await loadSelectionSuggestions(selection, scriptWithCandidate(target.value))
  }

  const updateSelectionReplacement = (value: string) => {
    setSelectionReplacement(value)
    setTextSelection({
      start: 0,
      end: value.length,
      text: value,
      x: 0,
      y: 0,
      scope: "candidate",
    })
    setSelectionSuggestions([])
    setSelectedSuggestionIds([])
    setFollowupSuggestions([])
  }

  const selectedSuggestions = selectionSuggestions.filter((item) =>
    selectedSuggestionIds.includes(item.id),
  )
  const combinedSelectionInstruction = [
    ...selectedSuggestions.map((item) => item.instruction),
    selectionInstruction.trim(),
  ]
    .filter(Boolean)
    .join("；")
  const selectionNeedsResearch = selectedSuggestions.some(
    (item) => item.evidence_needed,
  )

  const toggleSelectionSuggestion = (id: string) => {
    setSelectedSuggestionIds((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id],
    )
  }

  const runSelectionRewrite = async () => {
    if (
      !activeScript ||
      !draft ||
      !textSelection ||
      combinedSelectionInstruction.length < 2
    )
      return
    setSelectionRewriting(true)
    setError(null)
    try {
      const response = await rewriteScriptSelection({
        selected_text: textSelection.text,
        instruction: combinedSelectionInstruction,
        full_script:
          textSelection.scope === "candidate"
            ? scriptWithCandidate(selectionReplacement)
            : draft.spoken_script,
        account_type: activeScript.account_type,
        duration_seconds: activeScript.duration_seconds,
        tone: "保持当前版本语气",
        skill_name: activeScript.template_used,
        verified_facts: compactRewriteFacts(
          hotspotResult?.fact_verification?.verified_facts || [],
        ),
        verified_sources: hotspotResult?.fact_verification?.sources || [],
        rewrite_intents: selectedSuggestions.map((item) => item.label),
        research_mode: selectionNeedsResearch ? "targeted" : "none",
        emotional_goal:
          selectedSuggestions.find((item) => item.evidence_needed)?.reason ||
          "",
      })
      const formattedReplacement = formatSpeechParagraphs(response.replacement)
      const nextReplacement =
        textSelection.scope === "candidate"
          ? `${selectionReplacement.slice(0, textSelection.start)}${formattedReplacement}${selectionReplacement.slice(textSelection.end)}`
          : formattedReplacement
      setSelectionReplacement(nextReplacement)
      setSelectionChangeSummary(response.change_summary)
      setSelectionSupportingFacts(response.supporting_facts || [])
      setSelectionSources(response.sources || [])
      setTextSelection({
        start: 0,
        end: nextReplacement.length,
        text: nextReplacement,
        x: 0,
        y: 0,
        scope: "candidate",
      })
      setFollowupSuggestionsLoading(true)
      void fetchSelectionRewriteSuggestions({
        selected_text: nextReplacement,
        full_script: scriptWithCandidate(nextReplacement),
        account_type: activeScript.account_type,
        duration_seconds: activeScript.duration_seconds,
        tone: "保持当前版本语气",
        skill_name: activeScript.template_used,
        verified_facts: compactRewriteFacts([
          ...(hotspotResult?.fact_verification?.verified_facts || []),
          ...(response.supporting_facts || []),
        ]),
      })
        .then((suggestions) => {
          setFollowupSuggestions(suggestions.suggestions)
        })
        .catch(() => {
          setFollowupSuggestions([])
        })
        .finally(() => {
          setFollowupSuggestionsLoading(false)
        })
    } catch (event) {
      setError(event instanceof Error ? event.message : "Codex 局部改写失败")
    } finally {
      setSelectionRewriting(false)
    }
  }

  const applySelectionReplacement = () => {
    if (!draft || !sourceSelection || !selectionReplacement) return
    if (
      draft.spoken_script.slice(sourceSelection.start, sourceSelection.end) !==
      sourceSelection.text
    ) {
      setError("口播稿已经变化，请重新选择要修改的文字。")
      return
    }
    const nextScript = `${draft.spoken_script.slice(0, sourceSelection.start)}${selectionReplacement}${draft.spoken_script.slice(sourceSelection.end)}`
    applyDraft({
      spoken_script: formatSpeechParagraphs(nextScript),
      production_status: "editing",
    })
    const nextCaret = sourceSelection.start + selectionReplacement.length
    setTextSelection(null)
    setSourceSelection(null)
    setSelectionComposerOpen(false)
    setSelectionInstruction("")
    setSelectionReplacement("")
    setSelectionSuggestions([])
    setSelectedSuggestionIds([])
    setSelectionSupportingFacts([])
    setSelectionSources([])
    setFollowupSuggestions([])
    window.requestAnimationFrame(() => {
      scriptEditorRef.current?.focus()
      scriptEditorRef.current?.setSelectionRange(nextCaret, nextCaret)
    })
  }

  const applyFollowupSuggestion = (suggestion: SelectionRewriteSuggestion) => {
    const selection: TextSelection = {
      start: 0,
      end: selectionReplacement.length,
      text: selectionReplacement,
      x: 0,
      y: 0,
      scope: "candidate",
    }
    setTextSelection(selection)
    setSelectionSuggestions(followupSuggestions)
    setSelectedSuggestionIds([suggestion.id])
    setSelectionInstruction("")
    setFollowupSuggestions([])
  }
  const loadHumanReview = useCallback(async () => {
    setReviewLoading(true)
    setError(null)
    try {
      const response = await fetchHumanReviewTemplate()
      setReviewItems(response.items)
      if (!response.items.length) onToast(response.message)
    } catch (event) {
      setError(event instanceof Error ? event.message : "读取人审记录失败")
    } finally {
      setReviewLoading(false)
    }
  }, [onToast])

  useEffect(() => {
    if (!showDiagnostics && !onlyDiagnostics) return
    void loadHumanReview()
  }, [
    onlyDiagnostics,
    showDiagnostics,
    loadHumanReview,
  ])

  const createReviewTemplate = async () => {
    setReviewLoading(true)
    setError(null)
    try {
      await onCreateHumanReviewTemplate()
      const response = await fetchHumanReviewTemplate()
      setReviewItems(response.items)
    } catch (event) {
      setError(event instanceof Error ? event.message : "生成人审模板失败")
    } finally {
      setReviewLoading(false)
    }
  }

  const runReleaseEvaluation = async () => {
    setReleaseEvaluationLoading(true)
    setError(null)
    try {
      const result = await runSkillReleaseEvaluation()
      setReleaseEvaluation(result)
      onToast(result.message)
    } catch (event) {
      setError(event instanceof Error ? event.message : "真实 Skill 发布评测未能启动")
    } finally {
      setReleaseEvaluationLoading(false)
    }
  }

  const updateReviewItem = (id: string, updates: Partial<HumanReviewItem>) => {
    setReviewItems((current) =>
      current.map((item) => (item.id === id ? { ...item, ...updates } : item)),
    )
  }

  const saveHumanReview = async () => {
    setReviewSaving(true)
    setError(null)
    try {
      const response = await updateHumanReviewTemplate(reviewItems)
      setReviewItems(response.items)
      onToast(response.message)
      await onRefreshExternalGates()
    } catch (event) {
      setError(event instanceof Error ? event.message : "保存人审记录失败")
    } finally {
      setReviewSaving(false)
    }
  }

  const reviewPassedCount = reviewItems.filter(
    (item) =>
      item.shootable &&
      item.not_pure_rewrite &&
      item.clear_structure &&
      item.risk_passed,
  ).length
  const gatePassedCount =
    externalGates?.items.filter((item) => item.passed).length ?? 0
  const gateTotalCount = externalGates?.items.length || 3
  const normalizedLink = gateValue(externalGates?.link_gate, "normalized_link")
  const linkInput = gateValue(externalGates?.link_gate, "input_link")
  const llmMode = gateValue(externalGates?.llm_gate, "mode") || "offline"
  const llmModel =
    gateValue(externalGates?.llm_gate, "model") || "openai/gpt-4.1-mini"
  const humanPassed = gateNumber(
    externalGates?.human_review_gate,
    "passed_count",
  )
  const humanRequired =
    gateNumber(externalGates?.human_review_gate, "required_count") || 10
  const scriptListDescription = hotspotResult
    ? hotspotResult.scripts.length > 1
      ? `本次有 ${hotspotResult.scripts.length} 个文本结构。切换结构前会先保存当前填写内容。`
      : hotspotResult.generation_mode === "ai"
        ? "这是 Codex 生成的文本结构，不是成稿。请按段落填写正文，提交复核后才能导出。"
        : "这是本地结构工作稿，不代表 Codex 成稿。请先填写正文，再提交人工复核。"
    : "还没有本次生成结果时，显示最近保存的脚本。"

  const diagnosticsCard = (
    <Card className={onlyDiagnostics ? undefined : "full-span"}>
      <SectionHeader
        title="系统诊断"
        description="这里保留下载、模型、凭证、门禁和人审状态；运营主流程默认不展示。"
        action={
          <span
            className={`status-badge ${externalGates?.passed ? "status-badge-success" : "status-badge-warning"}`}
          >
            {externalGates?.passed ? "已通过" : "待补齐"}
          </span>
        }
      />
      <div className="gate-progress-panel">
        <div className="gate-progress-head">
          <div>
            <strong>v1 外部门禁</strong>
            <span>
              真实发布前确认链接提取、真实模型和人审质量；缺项不阻塞本地草稿。
            </span>
          </div>
          <span
            className={`status-badge ${externalGates?.passed ? "status-badge-success" : "status-badge-warning"}`}
          >
            {gatePassedCount}/{gateTotalCount}
          </span>
        </div>
        <div className="gate-progress-list">
          {(externalGates?.items || []).map((item, index) => (
            <div
              key={item.key}
              className={`gate-progress-step ${item.passed ? "is-complete" : ""}`}
            >
              <span>{item.passed ? "✓" : index + 1}</span>
              <div>
                <strong>{item.label}</strong>
                <small>
                  {item.passed ? "已通过" : item.action_items[0] || item.detail}
                </small>
              </div>
            </div>
          ))}
        </div>
        <div className="gate-readiness-grid">
          <div>
            <span>已解析链接</span>
            <strong>
              {normalizedLink || linkInput || "等待粘贴抖音分享文案或链接"}
            </strong>
          </div>
          <div>
            <span>模型配置</span>
            <strong>
              {llmMode} / {llmModel}
            </strong>
          </div>
          <div>
            <span>人工复核</span>
            <strong>
              {humanPassed}/{humanRequired}
            </strong>
          </div>
        </div>
      </div>
      <div className="gate-grid">
        {(externalGates?.items || []).map((item) => (
          <div key={item.key} className="gate-card">
            <div className="gate-card-head">
              <strong>{item.label}</strong>
              <span
                className={`status-badge ${item.passed ? "status-badge-success" : "status-badge-warning"}`}
              >
                {item.passed ? "通过" : item.status}
              </span>
            </div>
            <p>{item.detail}</p>
            {item.action_items.length ? (
              <ul>
                {item.action_items.slice(0, 3).map((action) => (
                  <li key={action}>{action}</li>
                ))}
              </ul>
            ) : null}
          </div>
        ))}
        {!externalGates ? (
          <div className="gate-card">
            <div className="gate-card-head">
              <strong>门禁状态</strong>
              <span className="status-badge status-badge-neutral">未加载</span>
            </div>
            <p>刷新后显示真实抖音链接、真实 LLM 和人工质量复核状态。</p>
          </div>
        ) : null}
      </div>
      <div className="export-actions">
        <button
          type="button"
          className="secondary-button"
          onClick={() => void onRefreshExternalGates()}
          disabled={externalGateLoading}
        >
          <RefreshCw size={16} />
          {externalGateLoading ? "刷新中..." : "刷新门禁"}
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={() =>
            void onRefreshExternalGates({ runLink: true, expectModel: true })
          }
          disabled={externalGateLoading}
        >
          <ShieldCheck size={16} />
          执行真实门禁
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={() => void runReleaseEvaluation()}
          disabled={releaseEvaluationLoading}
        >
          <ShieldCheck size={16} />
          {releaseEvaluationLoading ? "评测中..." : "运行 Skill 发布评测"}
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={() => void loadHumanReview()}
          disabled={reviewLoading}
        >
          <FileCheck2 size={16} />
          读取人审
        </button>
        <button
          type="button"
          className="secondary-button"
          onClick={() => void createReviewTemplate()}
          disabled={externalGateLoading || reviewLoading}
        >
          <FileCheck2 size={16} />
          生成人审模板
        </button>
        {releaseEvaluation ? (
          <span className="export-path">{releaseEvaluation.message}</span>
        ) : null}
      </div>
      <div className="human-review-panel">
        <div className="human-review-head">
          <div>
            <strong>人审记录</strong>
            <span>通过 {reviewPassedCount}/10。四项全部勾选才计入通过。</span>
          </div>
        </div>
        {reviewItems.length ? (
          <div
            className="human-review-table"
            role="table"
            aria-label="人工质量复核"
          >
            <div className="human-review-row human-review-row-head" role="row">
              <span>脚本</span>
              <span>可拍</span>
              <span>非复述</span>
              <span>结构清晰</span>
              <span>风险通过</span>
              <span>复核人 / 备注</span>
            </div>
            {reviewItems.map((item) => (
              <div key={item.id} className="human-review-row" role="row">
                <div>
                  <strong>{item.script_title || item.id}</strong>
                  <small>{item.hotspot || "待填写热点/角度"}</small>
                </div>
                {(
                  [
                    "shootable",
                    "not_pure_rewrite",
                    "clear_structure",
                    "risk_passed",
                  ] as const
                ).map((field) => (
                  <label key={field} className="review-check">
                    <input
                      type="checkbox"
                      checked={item[field]}
                      onChange={(event) =>
                        updateReviewItem(item.id, {
                          [field]: event.target.checked,
                        })
                      }
                    />
                  </label>
                ))}
                <div className="review-note-fields">
                  <input
                    value={item.reviewer}
                    placeholder="复核人"
                    onChange={(event) =>
                      updateReviewItem(item.id, {
                        reviewer: event.target.value,
                      })
                    }
                  />
                  <input
                    value={item.notes}
                    placeholder="备注"
                    onChange={(event) =>
                      updateReviewItem(item.id, { notes: event.target.value })
                    }
                  />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            title="尚无人审记录"
            description="先生成或读取人审模板，再在这里完成 10 条脚本人工复核。"
          />
        )}
        <div className="export-actions">
          <button
            type="button"
            className="primary-button"
            onClick={() => void saveHumanReview()}
            disabled={!reviewItems.length || reviewSaving}
          >
            <Save size={16} />
            {reviewSaving ? "保存中..." : "保存人审结果"}
          </button>
        </div>
      </div>
    </Card>
  )

  if (onlyDiagnostics) {
    return <div className="page-grid">{diagnosticsCard}</div>
  }

  if (!activeScript || !draft) {
    return (
      <Card>
        <EmptyState
          title="还没有可填写的结构稿"
          description="先去“生成结构”输入热点、大纲或半成品稿，系统核实事实并匹配 Skill 后生成文本结构，再进入填写。"
        />
      </Card>
    )
  }

  const payload = (): GeneratedScriptUpdatePayload => ({
    title: draft.title.trim() || activeScript.title,
    spoken_script: draft.spoken_script.trim(),
    shot_suggestions: splitLines(draft.shot_suggestions),
    subtitle_rhythm: splitLines(draft.subtitle_rhythm),
    comment_cta: draft.comment_cta.trim(),
    production_status: draft.production_status,
    version_label: draft.version_label.trim() || "v1",
    editor_note: draft.editor_note.trim() || null,
  })

  const draftIsDirty =
    JSON.stringify(payload()) !==
    JSON.stringify({
      title: activeScript.title,
      spoken_script: formatSpeechParagraphs(activeScript.spoken_script).trim(),
      shot_suggestions: activeScript.shot_suggestions,
      subtitle_rhythm: activeScript.subtitle_rhythm,
      comment_cta: activeScript.comment_cta,
      production_status: activeScript.production_status || "draft",
      version_label: activeScript.version_label || "v1",
      editor_note: activeScript.editor_note || null,
    })

  const save = async () => {
    setSaving(true)
    setError(null)
    try {
      const updated = await onUpdateScript(activeScript.id, payload())
      onSelectScript(updated)
      onToast("脚本生产单已保存")
    } catch (event) {
      setError(event instanceof Error ? event.message : "保存脚本失败")
    } finally {
      setSaving(false)
    }
  }

  const switchScript = async (script: GeneratedScript) => {
    if (
      script.id === activeScript.id ||
      selectionRewriting ||
      selectionSuggestionsLoading
    )
      return
    setSaving(true)
    setError(null)
    try {
      if (draftIsDirty) await onUpdateScript(activeScript.id, payload())
      onSelectScript(script)
      onToast(
        draftIsDirty
          ? `当前精修已保存，已切换到 ${script.version_label}`
          : `已切换到 ${script.version_label}`,
      )
    } catch (event) {
      setError(event instanceof Error ? event.message : "切换版本前保存失败")
    } finally {
      setSaving(false)
    }
  }

  const changeWorkflowStatus = async (status: ScriptProductionStatus) => {
    setSaving(true)
    setError(null)
    try {
      const nextPayload = { ...payload(), production_status: status }
      const updated = await onUpdateScript(activeScript.id, nextPayload)
      setDraft(draftFromScript(updated))
      onSelectScript(updated)
      onToast(
        status === "review_ready"
          ? "已提交复核，确认无误后即可导出"
          : "已退回精修",
      )
    } catch (event) {
      setError(event instanceof Error ? event.message : "更新发布流程失败")
    } finally {
      setSaving(false)
    }
  }

  const checks = finishChecks(activeScript, draft)
  const passedChecks = checks.filter((item) => item.passed).length
  const speechStats = speechLengthStatus(
    draft.spoken_script,
    activeScript.duration_seconds,
  )

  const exportScript = async (format: "markdown" | "json" | "copy") => {
    const next = { ...activeScript, ...payload() }
    if (format === "copy") {
      if (hasStructurePlaceholders(next.spoken_script)) {
        setError(
          "当前还是结构工作稿，请先把“你来填写”和写作建议替换成完整口播正文。",
        )
        return
      }
      try {
        await navigator.clipboard.writeText(
          formatSpeechParagraphs(next.spoken_script),
        )
        onToast("已复制排版后的纯口播稿")
      } catch {
        setError("无法写入剪贴板，请检查浏览器权限。")
      }
      return
    }
    const stem = `${next.title.replace(/[\\/:*?"<>|]/g, "-").slice(0, 48) || "douyin-script"}-${next.version_label || "v1"}`
    if (format === "markdown") {
      downloadFile(
        `${stem}.md`,
        markdownForScript(next),
        "text/markdown;charset=utf-8",
      )
      onToast("已导出 Markdown")
    } else {
      downloadFile(
        `${stem}.json`,
        JSON.stringify(next, null, 2),
        "application/json;charset=utf-8",
      )
      onToast("已导出 JSON")
    }
    const updated = await onUpdateScript(activeScript.id, {
      ...payload(),
      production_status: "exported",
    })
    setDraft(draftFromScript(updated))
    onSelectScript(updated)
  }

  const allChecksPassed = passedChecks === checks.length

  return (
    <div className="review-workspace">
      <Card className="review-sidebar-card">
        <SectionHeader title="脚本版本" description={scriptListDescription} />
        <div className="script-asset-list" aria-label="脚本版本列表">
          {scripts.map((script) => {
            const isActive = script.id === activeScript.id
            const itemSpeech = speechLengthStatus(
              isActive ? draft.spoken_script : script.spoken_script,
              script.duration_seconds,
            )
            return (
              <button
                key={script.id}
                type="button"
                className={`script-asset-row ${isActive ? "is-active-asset" : ""}`}
                aria-pressed={isActive}
                disabled={
                  saving || selectionRewriting || selectionSuggestionsLoading
                }
                onClick={() => void switchScript(script)}
              >
                <span className="script-asset-copy">
                  <span className="script-asset-direction">
                    <strong>{script.content_angle}</strong>
                    {isActive ? (
                      <em>
                        <CheckCircle2 size={14} />
                        当前
                      </em>
                    ) : null}
                  </span>
                  <span className="script-asset-title">
                    {isActive ? draft.title : script.title}
                  </span>
                  <small>
                    {script.version_label || "v1"} · {script.duration_seconds}{" "}
                    秒 · {itemSpeech.count} 字
                  </small>
                </span>
              </button>
            )
          })}
        </div>

        <div
          className="finish-check-panel finish-check-compact"
          aria-label="导出前检查"
        >
          <div className="finish-check-head">
            <div>
              <strong>导出门禁</strong>
              <span>先处理未通过项，再导出正式文件。</span>
            </div>
            <Badge tone={allChecksPassed ? "success" : "warning"}>
              {passedChecks}/{checks.length}
            </Badge>
          </div>
          <div className="finish-check-list">
            {checks.map((item) => (
              <div
                key={item.key}
                className={`finish-check-row ${item.passed ? "is-complete" : ""}`}
              >
                <span>{item.passed ? "✓" : "!"}</span>
                <div>
                  <strong>{item.label}</strong>
                  <small>{item.detail}</small>
                </div>
              </div>
            ))}
          </div>
        </div>

        <details className="quiet-disclosure risk-disclosure">
          <summary>
            <span>风险检查</span>
            <RiskBadge level={activeScript.risk_check.level} />
          </summary>
          {activeScript.risk_check.items.length ? (
            <div className="risk-item-list">
              {activeScript.risk_check.items.map((item) => (
                <div key={`${item.label}-${item.reason}`}>
                  <strong>{item.label}</strong>
                  <span>{item.reason}</span>
                  <small>建议：{item.rewrite}</small>
                </div>
              ))}
            </div>
          ) : (
            <p>当前脚本未命中默认高敏风险规则。</p>
          )}
        </details>
      </Card>

      <Card className="review-editor-card">
        <SectionHeader
          title="填写与交付"
          description="先按结构填写口播正文，再提交人工复核；导出会自动记录最终状态。"
          action={<RiskBadge level={activeScript.risk_check.level} />}
        />
        <ol className="review-flow-strip" aria-label="脚本交付流程">
          <li
            className={
              draft.production_status === "draft" ||
              draft.production_status === "editing"
                ? "is-active"
                : "is-done"
            }
          >
            <i>
              {draft.production_status === "review_ready" ||
              draft.production_status === "exported" ? (
                <Check size={12} />
              ) : (
                1
              )}
            </i>
            <span>
              <strong>填写正文</strong>
              <small>选中文字可反复调用 Codex</small>
            </span>
          </li>
          <li
            className={
              draft.production_status === "review_ready"
                ? "is-active"
                : draft.production_status === "exported"
                  ? "is-done"
                  : ""
            }
          >
            <i>
              {draft.production_status === "exported" ? <Check size={12} /> : 2}
            </i>
            <span>
              <strong>人工复核</strong>
              <small>确认事实、表达和发布风险</small>
            </span>
          </li>
          <li
            className={draft.production_status === "exported" ? "is-done" : ""}
          >
            <i>
              {draft.production_status === "exported" ? <Check size={12} /> : 3}
            </i>
            <span>
              <strong>导出交付</strong>
              <small>复制纯口播或下载制作稿</small>
            </span>
          </li>
        </ol>
        <div className="review-title-row">
          <label>
            <span>标题</span>
            <input
              value={draft.title}
              onChange={(event) =>
                applyEditorialDraft({ title: event.target.value })
              }
            />
          </label>
          <label>
            <span>版本</span>
            <input
              value={draft.version_label}
              onChange={(event) =>
                applyEditorialDraft({ version_label: event.target.value })
              }
            />
          </label>
          <div className="workflow-current-state">
            <span>当前阶段</span>
            <strong>{statusLabels[draft.production_status]}</strong>
          </div>
        </div>
        <div className="script-editor-heading">
          <label className="field-label" htmlFor="script-spoken">
            结构稿 / 口播正文
          </label>
          <div
            className={`speech-length-meter is-${speechStats.status}`}
            aria-label="口播时长评估"
          >
            <span>{speechStats.count} 字</span>
            <span>预计 {speechStats.estimatedSeconds} 秒</span>
            <strong>
              建议 {speechStats.minimum}-{speechStats.maximum} 字
            </strong>
          </div>
        </div>
        <div className="production-script-editor">
          <textarea
            ref={scriptEditorRef}
            id="script-spoken"
            className="text-area production-script-area"
            value={draft.spoken_script}
            readOnly={selectionRewriting || selectionSuggestionsLoading}
            onChange={(event) => {
              applyEditorialDraft({ spoken_script: event.target.value })
              setTextSelection(null)
              setSelectionReplacement("")
            }}
            onMouseUp={handleSelectionMouseUp}
            onKeyUp={handleSelectionKeyUp}
          />
          {textSelection && !selectionComposerOpen ? (
            <div
              className="selection-action-popover"
              style={{ left: textSelection.x, top: textSelection.y }}
            >
              <button
                type="button"
                onClick={() => void openSelectionComposer()}
              >
                <Sparkles size={15} />
                开始写作修改
              </button>
            </div>
          ) : null}
        </div>

        {sourceSelection && textSelection && selectionComposerOpen ? (
          <section
            className="selection-rewrite-panel"
            aria-label="局部改写"
            aria-busy={selectionRewriting || selectionSuggestionsLoading}
          >
            <header>
              <div>
                <span>
                  已选择 {textSelection.text.replace(/\s+/g, "").length} 字
                </span>
                <strong>
                  “{textSelection.text.slice(0, 70)}
                  {textSelection.text.length > 70 ? "..." : ""}”
                </strong>
              </div>
              <button
                type="button"
                className="icon-button"
                title="关闭局部改写"
                disabled={selectionRewriting || selectionSuggestionsLoading}
                onClick={() => {
                  setSelectionComposerOpen(false)
                  setSourceSelection(null)
                  setTextSelection(null)
                  setSelectionReplacement("")
                  setSelectedSuggestionIds([])
                }}
              >
                <X size={16} />
              </button>
            </header>
            <div className="selection-rewrite-suggestion-head">
              <span>针对这段的修改方向</span>
              <em>可多选</em>
            </div>
            {selectionSuggestionsLoading ? (
              <div className="selection-suggestion-loading">
                <LoaderCircle className="spin" size={15} />
                Codex 正在读取选区和上下文
              </div>
            ) : selectionSuggestions.length ? (
              <div
                className="selection-rewrite-suggestions"
                aria-label="针对选区的修改建议"
              >
                {selectionSuggestions.map((item) => {
                  const isSelected = selectedSuggestionIds.includes(item.id)
                  return (
                    <button
                      key={item.id}
                      type="button"
                      aria-pressed={isSelected}
                      className={isSelected ? "is-selected" : ""}
                      disabled={
                        selectionRewriting || selectionSuggestionsLoading
                      }
                      onClick={() => toggleSelectionSuggestion(item.id)}
                    >
                      <span>
                        <i>{isSelected ? <Check size={13} /> : null}</i>
                        <strong>{item.label}</strong>
                        {item.evidence_needed ? (
                          <em>
                            <Search size={11} />
                            需查证
                          </em>
                        ) : null}
                      </span>
                      <small>{item.reason}</small>
                    </button>
                  )
                })}
              </div>
            ) : null}
            {selectionSuggestionError ? (
              <p className="selection-suggestion-error">
                {selectionSuggestionError}
              </p>
            ) : null}
            <div className="selection-rewrite-composer">
              <input
                value={selectionInstruction}
                placeholder="还可以输入自己的修改要求"
                disabled={selectionRewriting || selectionSuggestionsLoading}
                onChange={(event) =>
                  setSelectionInstruction(event.target.value)
                }
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault()
                    void runSelectionRewrite()
                  }
                }}
              />
              <button
                type="button"
                className="primary-button"
                onClick={() => void runSelectionRewrite()}
                disabled={
                  selectionRewriting ||
                  selectionSuggestionsLoading ||
                  combinedSelectionInstruction.length < 2
                }
              >
                {selectionRewriting ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Sparkles size={16} />
                )}
                {selectionRewriting ? "Codex 改写中" : "生成改写"}
              </button>
            </div>
            {selectionReplacement ? (
              <div className="selection-rewrite-result">
                <div className="selection-rewrite-result-head">
                  <span>改写候选</span>
                  <em>{selectionChangeSummary}</em>
                </div>
                <textarea
                  ref={rewriteCandidateRef}
                  className="rewrite-candidate-area"
                  aria-label="改写候选"
                  value={selectionReplacement}
                  readOnly={selectionRewriting || selectionSuggestionsLoading}
                  onChange={(event) =>
                    updateSelectionReplacement(event.target.value)
                  }
                  onMouseUp={(event) =>
                    void handleCandidateSelection(event.currentTarget)
                  }
                  onKeyUp={(event) => {
                    if (
                      event.shiftKey ||
                      [
                        "ArrowLeft",
                        "ArrowRight",
                        "ArrowUp",
                        "ArrowDown",
                      ].includes(event.key)
                    ) {
                      void handleCandidateSelection(event.currentTarget)
                    }
                  }}
                />
                <small className="rewrite-candidate-hint">
                  可以直接编辑，也可以选中候选稿里的文字继续优化。
                </small>
                {selectionSupportingFacts.length || selectionSources.length ? (
                  <details className="selection-rewrite-evidence">
                    <summary>
                      <Link2 size={13} />
                      本次补写依据
                    </summary>
                    {selectionSupportingFacts.map((item) => (
                      <span key={item}>{item}</span>
                    ))}
                    {selectionSources.map((source) => (
                      <a
                        key={source.url}
                        href={source.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {source.publisher || source.title}
                      </a>
                    ))}
                  </details>
                ) : null}
                {followupSuggestionsLoading ? (
                  <div className="selection-suggestion-loading">
                    <LoaderCircle className="spin" size={14} />
                    正在根据候选稿生成下一轮建议
                  </div>
                ) : followupSuggestions.length ? (
                  <div className="rewrite-followups">
                    <span>继续优化建议</span>
                    <div>
                      {followupSuggestions.slice(0, 4).map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          disabled={selectionRewriting}
                          onClick={() => applyFollowupSuggestion(item)}
                        >
                          <strong>{item.label}</strong>
                          <small>{item.reason}</small>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div
                  className="selection-result-actions"
                  ref={selectionActionsRef}
                >
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={selectionRewriting || selectionSuggestionsLoading}
                    onClick={() => {
                      setSelectionReplacement("")
                      setFollowupSuggestions([])
                      setTextSelection(sourceSelection)
                    }}
                  >
                    放弃候选
                  </button>
                  <button
                    type="button"
                    className="primary-button"
                    disabled={selectionRewriting || selectionSuggestionsLoading}
                    onClick={applySelectionReplacement}
                  >
                    采用到口播稿
                  </button>
                </div>
              </div>
            ) : null}
          </section>
        ) : null}

        <details className="production-details">
          <summary>
            制作信息 <span>分镜、字幕节奏、评论引导与编辑备注</span>
          </summary>
          <div className="production-edit-grid">
            <label>
              <span>评论引导</span>
              <input
                value={draft.comment_cta}
                onChange={(event) =>
                  applyEditorialDraft({ comment_cta: event.target.value })
                }
              />
            </label>
            <label>
              <span>编辑备注</span>
              <textarea
                className="text-area compact-text-area"
                value={draft.editor_note}
                onChange={(event) =>
                  applyEditorialDraft({ editor_note: event.target.value })
                }
              />
            </label>
            <label>
              <span>分镜建议（每行一条）</span>
              <textarea
                className="text-area compact-text-area"
                value={draft.shot_suggestions}
                onChange={(event) =>
                  applyEditorialDraft({ shot_suggestions: event.target.value })
                }
              />
            </label>
            <label>
              <span>字幕节奏（每行一条）</span>
              <textarea
                className="text-area compact-text-area"
                value={draft.subtitle_rhythm}
                onChange={(event) =>
                  applyEditorialDraft({ subtitle_rhythm: event.target.value })
                }
              />
            </label>
          </div>
          {activeScript.preset_application?.length ? (
            <div className="mini-list">
              <strong>套用说明</strong>
              {activeScript.preset_application.map((item) => (
                <span key={item}>{item}</span>
              ))}
            </div>
          ) : null}
        </details>
        {error ? <div className="alert-box alert-error">{error}</div> : null}
        <div className="review-export-footer">
          <span className={allChecksPassed ? "is-ready" : ""}>
            {draft.production_status === "review_ready"
              ? "当前为待复核稿，确认后可正式导出"
              : draft.production_status === "exported"
                ? "该版本已导出；继续修改会回到精修状态"
                : "当前处于精修阶段，保存后提交人工复核"}
          </span>
          <div>
            <button
              type="button"
              className="primary-button"
              onClick={() => void save()}
              disabled={saving}
            >
              <Save size={16} />
              {saving ? "保存中..." : "保存修改"}
            </button>
            {draft.production_status === "review_ready" ||
            draft.production_status === "exported" ? (
              <button
                type="button"
                className="secondary-button"
                disabled={saving}
                onClick={() => void changeWorkflowStatus("editing")}
              >
                退回精修
              </button>
            ) : (
              <button
                type="button"
                className="secondary-button"
                disabled={
                  saving ||
                  checks.some((item) => item.key !== "human" && !item.passed)
                }
                onClick={() => void changeWorkflowStatus("review_ready")}
              >
                <FileCheck2 size={16} />
                提交复核
              </button>
            )}
            <button
              type="button"
              className="secondary-button"
              onClick={() => void exportScript("copy")}
            >
              <Copy size={16} />
              复制口播正文
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void exportScript("markdown")}
              disabled={!allChecksPassed}
            >
              <Download size={16} />
              Markdown
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => void exportScript("json")}
              disabled={!allChecksPassed}
            >
              <Download size={16} />
              JSON
            </button>
          </div>
        </div>
      </Card>

      {showDiagnostics ? diagnosticsCard : null}
    </div>
  )
}
