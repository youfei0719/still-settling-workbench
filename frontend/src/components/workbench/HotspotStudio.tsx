import {
  Check,
  ChevronDown,
  FileOutput,
  FileText,
  Library,
  LoaderCircle,
  PencilLine,
  PlusCircle,
  Search,
  ShieldCheck,
  Sparkles,
  WandSparkles,
} from "lucide-react"
import { useEffect, useState } from "react"
import { formatSpeechParagraphs, speechLengthStatus } from "@/lib/speech"
import type {
  DraftInputType,
  DraftRewriteActivity,
  DraftRewriteResponse,
  DraftRewriteTask,
  GeneratedScript,
  TemplatePattern,
} from "@/types/workbench"
import { Badge, Card, EmptyState, RiskBadge, SectionHeader } from "./ui"

function activityIcon(activity: DraftRewriteActivity) {
  if (activity.kind === "search" || activity.kind === "source") return Search
  if (activity.kind === "skill") return Library
  if (activity.kind === "draft") return PencilLine
  if (activity.kind === "check") return Check
  return Sparkles
}

function skillOptionLabel(template: TemplatePattern) {
  const scene =
    template.applicable_scenes?.[0] ||
    template.hotspot_types[0] ||
    template.account_type
  return `${template.name}｜${scene}`
}

function factVerdictLabel(result: DraftRewriteResponse) {
  const verdict = result.fact_verification?.verdict
  if (verdict === "verified") return "已核实"
  if (verdict === "refuted") return "与公开来源不符"
  if (verdict === "uncertain") return "来源存在冲突"
  if (verdict === "failed") return "核验未完成"
  return "无需专项核验"
}

export function HotspotStudio({
  orderTitle,
  materialText,
  hasDissection,
  hotspot,
  draftInputType,
  accountType,
  templates,
  selectedTemplateId,
  selectedScriptId,
  duration,
  tone,
  goal,
  loading,
  generationTask,
  error,
  result,
  onHotspotChange,
  onDraftInputTypeChange,
  onAccountTypeChange,
  onTemplateChange,
  onSelectScript,
  onDurationChange,
  onToneChange,
  onGoalChange,
  onGenerate,
  onOpenSkillLibrary,
  onOpenCreateTask,
  onGoExport,
}: {
  orderTitle: string
  materialText: string
  hasDissection: boolean
  hotspot: string
  draftInputType: DraftInputType
  accountType: string
  templates: TemplatePattern[]
  selectedTemplateId: string | null
  selectedScriptId: string | null
  duration: number
  tone: string
  goal: string
  loading: boolean
  generationTask: DraftRewriteTask | null
  error: string | null
  result: DraftRewriteResponse | null
  onHotspotChange: (value: string) => void
  onDraftInputTypeChange: (value: DraftInputType) => void
  onAccountTypeChange: (value: string) => void
  onTemplateChange: (value: string | null) => void
  onSelectScript: (script: GeneratedScript) => void
  onDurationChange: (value: number) => void
  onToneChange: (value: string) => void
  onGoalChange: (value: string) => void
  onGenerate: () => void
  onOpenSkillLibrary: () => void
  onOpenCreateTask: () => void
  onGoExport: () => void
}) {
  const [composerExpanded, setComposerExpanded] = useState(true)
  const selectedTemplate =
    templates.find((template) => template.id === selectedTemplateId) || null
  const activeTemplates = templates
    .filter((template) => !template.disabled_reason)
    .sort(
      (a, b) =>
        (b.quality_score || 80) - (a.quality_score || 80) ||
        b.usage_count - a.usage_count,
    )
  const accountTemplates = activeTemplates.filter(
    (template) => template.account_type === accountType,
  )
  const templateOptions = accountTemplates.length
    ? accountTemplates
    : activeTemplates
  const hasSkills = activeTemplates.length > 0
  const canGenerate = hasSkills && hotspot.trim().length >= 4 && !loading
  const activeScript =
    result?.scripts.find((script) => script.id === selectedScriptId) ||
    result?.scripts[0] ||
    null
  const activeSpeechStatus = activeScript
    ? speechLengthStatus(
        activeScript.spoken_script,
        activeScript.duration_seconds,
      )
    : null
  const primaryMatch = result?.matched_skills[0] || null
  const activities = generationTask?.activities || []
  const currentActivity = activities[activities.length - 1]
  const lastVerifiedActivity = [...activities]
    .reverse()
    .find((activity) => !activity.title.startsWith("等待"))
  const visibleActivities = [...activities]
    .reverse()
    .filter(
      (activity) =>
        activity.id !== currentActivity?.id &&
        !activity.title.startsWith("等待"),
    )
    .slice(0, 6)
  const completedActivityCount = activities.filter(
    (activity) => activity.status === "completed",
  ).length
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const stageIndex = {
    queued: 0,
    diagnosing: 0,
    fact_checking: 1,
    matching_skill: 2,
    generating_scripts: 2,
    quality_checking: 3,
    completed: 4,
    failed: 4,
  }[generationTask?.stage || "queued"]
  const generationStages = ["理解任务", "核实来源", "匹配 Skill", "生成结构"]

  useEffect(() => {
    if (result) setComposerExpanded(false)
  }, [result])

  useEffect(() => {
    if (!loading || !generationTask?.created_at) {
      setElapsedSeconds(0)
      return
    }
    const startedAt = new Date(generationTask.created_at).getTime()
    const updateElapsed = () =>
      setElapsedSeconds(
        Math.max(0, Math.round((Date.now() - startedAt) / 1000)),
      )
    updateElapsed()
    const timer = window.setInterval(updateElapsed, 1000)
    return () => window.clearInterval(timer)
  }, [generationTask?.created_at, loading])

  function versionSummary(script: GeneratedScript) {
    const positioning = script.preset_application?.find((item) =>
      item.startsWith("本版重点："),
    )
    return positioning?.replace("本版重点：", "") || script.content_angle
  }

  return (
    <div className="studio-page">
      <Card className={`studio-composer ${result ? "has-result" : ""}`}>
        <SectionHeader
          title="生成文本结构"
          description="输入目标，系统会先查证关键事实，再匹配 Skill 生成可填写的文本结构。"
          action={
            result ? (
              <button
                type="button"
                className="ghost-button"
                onClick={() => setComposerExpanded((current) => !current)}
              >
                <PencilLine size={15} />
                {composerExpanded ? "收起需求" : "修改需求"}
              </button>
            ) : (
              <button
                type="button"
                className="ghost-button"
                onClick={onOpenCreateTask}
              >
                <PlusCircle size={15} />
                沉淀 Skill
              </button>
            )
          }
        />

        <section className="studio-context-line" aria-label="当前写作上下文">
          <span>
            <strong>当前任务</strong>
            {orderTitle}
          </span>
          <span>
            <strong>素材</strong>
            {materialText
              ? `${Math.min(materialText.length, 9999)} 字`
              : "直接输入主题"}
          </span>
          <span>
            <strong>能力库</strong>
            {hasDissection
              ? "含视频拆解"
              : `${activeTemplates.length} 个 Skill`}
          </span>
        </section>

        {result && !composerExpanded ? (
          <div className="studio-collapsed-brief">
            <div>
              <span>本次需求</span>
              <strong>{hotspot}</strong>
            </div>
            <div>
              <span>生成设置</span>
              <strong>{`${accountType} · ${duration} 秒 · ${tone} · ${goal}`}</strong>
            </div>
            <div>
              <span>指定 Skill</span>
              <strong>
                {selectedTemplate?.name ||
                  primaryMatch?.skill.name ||
                  "自动匹配"}
              </strong>
            </div>
          </div>
        ) : null}

        <fieldset
          className={`studio-composer-body ${composerExpanded ? "" : "is-collapsed"}`}
          disabled={loading}
        >
          {!hasSkills ? (
            <div className="alert-box alert-warning">
              <strong>还没有可用写作 Skill</strong>
              <span>
                请先用真实视频稿件沉淀至少一个 Skill，再回到这里生成。
              </span>
            </div>
          ) : null}

          <div className="studio-brief-grid">
            <div className="studio-primary-input">
              <label className="field-label" htmlFor="hotspot">
                你要写什么
              </label>
              <textarea
                id="hotspot"
                className="text-area hotspot-area"
                value={hotspot}
                onChange={(event) => onHotspotChange(event.target.value)}
                placeholder="写下热点、创作目标和你已经知道的材料。涉及重大事实时，系统会先联网核实。"
              />
              <div className="studio-input-footnote">
                <ShieldCheck size={14} />
                重大事实会先查证来源，不会把你的输入直接当作证据。
              </div>
            </div>

            <div className="studio-settings">
              <div className="studio-setting-grid">
                <label>
                  <span>输入类型</span>
                  <select
                    id="draft-input-type"
                    aria-label="输入类型"
                    value={draftInputType}
                    onChange={(event) =>
                      onDraftInputTypeChange(
                        event.target.value as DraftInputType,
                      )
                    }
                  >
                    <option value="hotspot">只有热点/想法</option>
                    <option value="outline">粗糙大纲</option>
                    <option value="partial_script">半成品脚本</option>
                    <option value="script">完整脚本，需要优化</option>
                  </select>
                </label>
                <label>
                  <span>视频时长</span>
                  <select
                    value={duration}
                    onChange={(event) =>
                      onDurationChange(Number(event.target.value))
                    }
                  >
                    <option value={30}>30 秒</option>
                    <option value={45}>45 秒</option>
                    <option value={60}>60 秒</option>
                    <option value={90}>90 秒</option>
                  </select>
                </label>
                <label>
                  <span>账号类型</span>
                  <select
                    value={accountType}
                    onChange={(event) =>
                      onAccountTypeChange(event.target.value)
                    }
                  >
                    <option>娱乐吃瓜号</option>
                    <option>泛娱乐观点号</option>
                    <option>商业分析号</option>
                    <option>情感观点号</option>
                    <option>社会观察号</option>
                  </select>
                </label>
                <label>
                  <span>语气</span>
                  <input
                    value={tone}
                    onChange={(event) => onToneChange(event.target.value)}
                  />
                </label>
              </div>

              <label className="studio-skill-select" htmlFor="writing-preset">
                <span>写作 Skill</span>
                <select
                  id="writing-preset"
                  value={selectedTemplateId || ""}
                  onChange={(event) =>
                    onTemplateChange(event.target.value || null)
                  }
                  disabled={!hasSkills}
                >
                  <option value="">自动匹配最适合的 Skill</option>
                  {templateOptions.map((template) => (
                    <option key={template.id} value={template.id}>
                      {skillOptionLabel(template)}
                    </option>
                  ))}
                </select>
              </label>

              <div className="studio-goal-row">
                <label>
                  <span>传播目标</span>
                  <input
                    value={goal}
                    onChange={(event) => onGoalChange(event.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="icon-text-button"
                  onClick={onOpenSkillLibrary}
                >
                  <Library size={15} />
                  Skill 库
                </button>
              </div>
            </div>
          </div>

          {selectedTemplate ? (
            <div className="selected-skill-contract">
              <span>已指定 Skill</span>
              <strong>{selectedTemplate.name}</strong>
              <em>生成时会逐步检查骨架覆盖，不只借用名称。</em>
            </div>
          ) : null}
          {error ? <div className="alert-box alert-error">{error}</div> : null}
          <div className="studio-submit-row">
            <span>
              {loading
                ? generationTask?.stage_detail || "正在创建生成任务"
                : "核实事实 → 匹配 Skill → 生成文本结构"}
            </span>
            <button
              type="button"
              className="primary-button studio-generate-button"
              onClick={onGenerate}
              disabled={!canGenerate}
            >
              {loading ? (
                <LoaderCircle className="spin" size={17} />
              ) : (
                <Sparkles size={17} />
              )}
              {loading ? "正在生成" : "核实事实并生成结构"}
            </button>
          </div>
        </fieldset>
      </Card>

      {loading ? (
        <Card className="generation-live-card" aria-live="polite">
          <header className="generation-live-header">
            <div className="generation-live-mark" aria-hidden="true">
              <LoaderCircle className="spin" size={18} />
            </div>
            <div>
              <span>当前真实状态</span>
              <h2>
                {currentActivity?.title ||
                  generationTask?.stage_detail ||
                  "正在启动 Codex"}
              </h2>
              <p>{currentActivity?.detail || "等待第一个可验证事件。"}</p>
              {currentActivity?.title.startsWith("等待") &&
              lastVerifiedActivity ? (
                <small>
                  最近完成：{lastVerifiedActivity.title} ·{" "}
                  {lastVerifiedActivity.detail}
                </small>
              ) : null}
            </div>
            <div className="generation-live-time">
              <strong>{elapsedSeconds}s</strong>
              <span>实际耗时</span>
            </div>
          </header>

          <ol className="generation-stage-strip" aria-label="真实生成阶段">
            {generationStages.map((label, index) => (
              <li
                key={label}
                className={
                  index < stageIndex
                    ? "is-done"
                    : index === stageIndex
                      ? "is-active"
                      : ""
                }
              >
                <i>{index < stageIndex ? <Check size={12} /> : index + 1}</i>
                <span>{label}</span>
              </li>
            ))}
          </ol>

          <details className="generation-event-history" open>
            <summary>
              <span>最近工作记录</span>
              <em>{completedActivityCount} 个动作已完成 · 最新在最上</em>
            </summary>
            <div className="codex-activity-log">
              {visibleActivities.map((activity) => {
                const Icon = activityIcon(activity)
                return (
                  <div
                    key={activity.id}
                    className={`codex-activity-row is-${activity.status}`}
                  >
                    <i>
                      {activity.status === "active" ? (
                        <LoaderCircle className="spin" size={13} />
                      ) : (
                        <Icon size={13} />
                      )}
                    </i>
                    <span>
                      <strong>{activity.title}</strong>
                      {activity.detail ? <em>{activity.detail}</em> : null}
                    </span>
                    <time>
                      {new Date(activity.created_at).toLocaleTimeString(
                        "zh-CN",
                        {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        },
                      )}
                    </time>
                  </div>
                )
              })}
            </div>
          </details>
          <footer>
            这里仅显示 Codex 返回的搜索、来源、Skill
            与结构事件；等待时间不会伪装成完成进度。
          </footer>
        </Card>
      ) : null}

      {!loading && result ? (
        <div className="studio-result-layout">
          <aside className="studio-decision-rail">
            <section
              className={`fact-evidence-panel is-${result.fact_verification?.verdict || "not_required"}`}
            >
              <div
                className={`result-generation-mode is-${result.generation_mode || "fallback"}`}
              >
                <Sparkles size={14} />
                <span>
                  <strong>
                    {result.generation_mode === "ai"
                      ? result.scripts.length > 1
                        ? "AI 文本结构 · 待选"
                        : "AI 文本结构 · 待填写"
                      : result.generation_mode === "blocked"
                        ? "生成已停止"
                        : "本地结构工作稿"}
                  </strong>
                  <em>{result.generation_note}</em>
                </span>
              </div>
              <div className="fact-evidence-heading">
                <ShieldCheck size={17} />
                <div>
                  <span>事实核验</span>
                  <strong>{factVerdictLabel(result)}</strong>
                </div>
              </div>
              {result.fact_verification?.summary ? (
                <p>{result.fact_verification.summary}</p>
              ) : (
                <p>输入中没有需要专项查证的重大事实。</p>
              )}
              {result.fact_verification?.corrections?.length ? (
                <div className="fact-corrections">
                  <strong>已校正</strong>
                  {result.fact_verification.corrections.map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </div>
              ) : null}
              {result.fact_verification?.sources?.length ? (
                <details className="fact-source-details">
                  <summary>
                    查看 {result.fact_verification.sources.length} 个公开来源{" "}
                    <ChevronDown size={14} />
                  </summary>
                  <div>
                    {result.fact_verification.sources.map((source) => (
                      <a
                        key={source.url}
                        href={source.url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <strong>{source.publisher || source.title}</strong>
                        <span>{source.title}</span>
                      </a>
                    ))}
                  </div>
                </details>
              ) : null}
            </section>

            {primaryMatch ? (
              <section className="skill-contract-panel">
                <span>本次采用 Skill</span>
                <strong>{primaryMatch.skill.name}</strong>
                <p>{primaryMatch.reason}</p>
                <details>
                  <summary>
                    查看执行骨架 <ChevronDown size={14} />
                  </summary>
                  <ol>
                    {primaryMatch.skill.skeleton.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                </details>
              </section>
            ) : null}

            {result.scripts.length > 1 ? (
              <section className="version-rail" aria-label="脚本创作方向">
                <div className="version-rail-heading">
                  <span>选择方向</span>
                  <em>{result.scripts.length} 个版本</em>
                </div>
                {result.scripts.map((script) => {
                  const isActive = script.id === activeScript?.id
                  return (
                    <button
                      key={script.id}
                      type="button"
                      aria-pressed={isActive}
                      className={isActive ? "is-active" : ""}
                      onClick={() => onSelectScript(script)}
                    >
                      <span>
                        {script.version_label || script.content_angle}
                      </span>
                      <strong>{script.content_angle}</strong>
                      <em>{versionSummary(script)}</em>
                    </button>
                  )
                })}
              </section>
            ) : null}

            <details className="diagnosis-compact">
              <summary>
                查看 AI 写作诊断 <ChevronDown size={14} />
              </summary>
              <div>
                <span>主要缺口</span>
                <p>{result.diagnosis.problems.join(" / ")}</p>
              </div>
              <div>
                <span>重构目标</span>
                <p>{result.diagnosis.rewrite_goals.join(" / ")}</p>
              </div>
            </details>
          </aside>

          {activeScript ? (
            <Card className="studio-script-canvas">
              <header className="focused-script-header">
                <div>
                  <div className="script-angle-row">
                    <Badge>
                      {result.scripts.length > 1
                        ? "步骤 1 / 3 · 选择方向"
                        : "步骤 1 / 3 · 文本结构"}
                    </Badge>
                    <Badge tone="accent">{activeScript.content_angle}</Badge>
                    <Badge tone="success">正在预览</Badge>
                  </div>
                  <h2>{activeScript.title}</h2>
                  <div className="focused-script-meta">
                    <span>{activeSpeechStatus?.count} 字</span>
                    <span>预计 {activeSpeechStatus?.estimatedSeconds} 秒</span>
                    <span className={`is-${activeSpeechStatus?.status}`}>
                      参考约 {activeScript.duration_seconds} 秒
                    </span>
                    <span>{activeScript.template_used}</span>
                  </div>
                </div>
                <RiskBadge level={activeScript.risk_check.level} />
              </header>

              <section className="script-artifact" aria-label="文本结构工作稿">
                <div className="script-artifact-heading">
                  <span>
                    <FileText size={15} />
                    文本结构工作稿
                  </span>
                  <em>
                    {result.scripts.length > 1
                      ? "选定后填写正文"
                      : "下一步填写正文"}
                  </em>
                </div>
                <div className="focused-script-copy">
                  {formatSpeechParagraphs(activeScript.spoken_script)}
                </div>
              </section>

              <details className="script-support-details">
                <summary>
                  查看 Skill 覆盖和拍摄提示 <ChevronDown size={15} />
                </summary>
                {activeScript.preset_application?.length ? (
                  <div className="mini-list">
                    <strong>Skill 执行证据</strong>
                    {activeScript.preset_application.map((item) => (
                      <span key={item}>{item}</span>
                    ))}
                  </div>
                ) : null}
                <div className="mini-list">
                  <strong>镜头建议</strong>
                  {activeScript.shot_suggestions.map((item) => (
                    <span key={item}>{item}</span>
                  ))}
                </div>
              </details>

              <div className="focused-script-action">
                <span>
                  {result.scripts.length > 1
                    ? "选定结构后进入填写；这里不是最终可发布稿。"
                    : "这是结构工作稿，不是最终可发布稿；下一步按段落填写正文。"}
                </span>
                <button
                  type="button"
                  className="primary-button"
                  onClick={() => {
                    onSelectScript(activeScript)
                    onGoExport()
                  }}
                >
                  <FileOutput size={15} />
                  {result.scripts.length > 1
                    ? "选定结构，开始填写"
                    : "开始填写正文"}
                </button>
              </div>
            </Card>
          ) : (
            <Card className="studio-blocked-canvas">
              <EmptyState
                title="事实核验未通过，未生成结构"
                description={
                  result.generation_note || "请查看左侧核验结论后重试。"
                }
              />
              <button
                type="button"
                className="primary-button"
                onClick={onGenerate}
              >
                <Search size={15} />
                重新联网核验
              </button>
            </Card>
          )}
        </div>
      ) : null}

      {!loading && !result ? (
        <div className="studio-empty-strip">
          <div>
            <Search size={18} />
            <span>
              <strong>先查证</strong>
              <em>核实重大事实和来源</em>
            </span>
          </div>
          <div>
            <Library size={18} />
            <span>
              <strong>再匹配</strong>
              <em>按写作缺口选择 Skill</em>
            </span>
          </div>
          <div>
            <WandSparkles size={18} />
            <span>
              <strong>后生成</strong>
              <em>输出一份可填写的文本结构</em>
            </span>
          </div>
        </div>
      ) : null}
    </div>
  )
}
