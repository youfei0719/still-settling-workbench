import {
  Archive,
  CheckCircle2,
  ExternalLink,
  GitMerge,
  Library,
  PlusCircle,
  Sparkles,
  UploadCloud,
} from "lucide-react"
import { useEffect, useState } from "react"
import type {
  AnalyzeTextResponse,
  CodexSkillPackResponse,
  CodexSkillPublishResponse,
  ScriptAnalysis,
  TemplatePattern,
  WritingPresetCreatePayload,
} from "@/types/workbench"
import { Badge, Card, EmptyState, RiskBadge, SectionHeader } from "./ui"

type PresetDraftForm = {
  name: string
  applicableScenes: string
  unsuitableScenes: string
  skeleton: string
}

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

function skillMatchSignals(analysis: AnalyzeTextResponse) {
  if (analysis.preset_draft.match_signals?.length)
    return analysis.preset_draft.match_signals
  return [
    analysis.preset_draft.name,
    analysis.analysis.content_angle,
    analysis.analysis.account_type,
    ...analysis.preset_draft.hotspot_types,
    ...analysis.analysis.template_suggestions.slice(0, 3),
  ].filter(Boolean)
}

export function AnalysisWorkspace({
  analysis,
  recentAnalyses,
  onSavePreset,
  savingPreset,
  savedSkill,
  onStartAnother,
  onOpenSkillLibrary,
  onPublishSkillPack,
  templates,
  skillPack,
  skillPublishing,
  skillPublishError,
  skillPublishResult,
  preselectedMergeTargetId,
}: {
  analysis: AnalyzeTextResponse | null
  recentAnalyses: ScriptAnalysis[]
  onSavePreset: (payload: WritingPresetCreatePayload) => Promise<void> | void
  savingPreset: boolean
  savedSkill: TemplatePattern | null
  onStartAnother: () => void
  onOpenSkillLibrary: () => void
  onPublishSkillPack: () => void
  templates: TemplatePattern[]
  skillPack: CodexSkillPackResponse | null
  skillPublishing: boolean
  skillPublishError: string | null
  skillPublishResult: CodexSkillPublishResponse | null
  preselectedMergeTargetId: string | null
}) {
  const [draftForm, setDraftForm] = useState<PresetDraftForm | null>(null)
  const [mergeTargetId, setMergeTargetId] = useState("new")

  useEffect(() => {
    if (!analysis) {
      setDraftForm(null)
      return
    }
    setDraftForm({
      name: analysis.preset_draft.name,
      applicableScenes: listToText(analysis.preset_draft.applicable_scenes),
      unsuitableScenes: listToText(analysis.preset_draft.unsuitable_scenes),
      skeleton: listToText(analysis.preset_draft.skeleton),
    })
    setMergeTargetId(
      preselectedMergeTargetId || analysis.preset_draft.similar_skill_id || "new",
    )
  }, [analysis?.preset_draft.id, analysis, preselectedMergeTargetId])

  if (!analysis) {
    if (recentAnalyses.length) {
      return (
        <div className="page-grid page-grid-two">
          <Card className="wide-card">
            <SectionHeader
              title="最近拆解记录"
              description="当前还没有新的灵感拆解结果，先展示演示样本，便于理解系统会提炼什么样的写作 Skill。"
            />
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>样例</th>
                    <th>账号类型</th>
                    <th>内容角度</th>
                    <th>冲突点</th>
                    <th>可沉淀写法</th>
                  </tr>
                </thead>
                <tbody>
                  {recentAnalyses.map((item) => (
                    <tr key={item.id}>
                      <td>
                        <strong>{item.hook}</strong>
                        <span>{item.emotion_curve.join(" -> ")}</span>
                      </td>
                      <td>{item.account_type}</td>
                      <td>{item.content_angle}</td>
                      <td>{item.conflict}</td>
                      <td>{item.reusable_template}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <SectionHeader
              title="样例写法拆解"
              description="默认选取第一条样例展示它为什么可借鉴。"
            />
            <div className="demo-analysis-detail">
              <span className="eyebrow-text">开头钩子</span>
              <strong>{recentAnalyses[0].hook}</strong>
              <span className="eyebrow-text">反转/升维</span>
              <p>{recentAnalyses[0].reversal}</p>
              <span className="eyebrow-text">结尾引导</span>
              <p>{recentAnalyses[0].ending_cta}</p>
              <div className="mini-list">
                <strong>结构骨架</strong>
                {recentAnalyses[0].structure.map((segment) => (
                  <span key={segment.name}>
                    {segment.name}：{segment.summary}
                  </span>
                ))}
              </div>
            </div>
          </Card>
        </div>
      )
    }

    return (
      <Card>
        <EmptyState
          title="还没有灵感拆解结果"
          description="先在灵感入库页提交一个视频、字幕或口播文本，系统会提炼可复用写作 Skill。"
        />
      </Card>
    )
  }

  const draft = analysis.preset_draft
  const mergeCandidates = templates.filter(
    (template) => template.status !== "retired" && !template.disabled_reason,
  )
  const mergeTarget = mergeCandidates.find(
    (template) => template.id === mergeTargetId,
  )
  const sourceUrl = analysis.source_video.url || draft.source_url
  const sourceAuthor = analysis.source_video.author || draft.source_author
  const savePayload: WritingPresetCreatePayload = {
    preset_draft: {
      ...draft,
      name: draftForm?.name.trim() || draft.name,
      applicable_scenes: textToList(draftForm?.applicableScenes || ""),
      unsuitable_scenes: textToList(draftForm?.unsuitableScenes || ""),
      skeleton: textToList(draftForm?.skeleton || "").length
        ? textToList(draftForm?.skeleton || "")
        : draft.skeleton,
    },
    name: draftForm?.name.trim() || draft.name,
    quality_score: 86,
    applicable_scenes: textToList(draftForm?.applicableScenes || ""),
    unsuitable_scenes: textToList(draftForm?.unsuitableScenes || ""),
    last_review_note: "基于来源样本提炼的结构能力，已人工确认可复用。",
    merge_target_id: mergeTarget?.id || null,
    merge_as_new: mergeTargetId === "new",
  }

  return (
    <div className="page-grid page-grid-two">
      <Card className="wide-card">
        <div className="source-summary">
          <div>
            <span>来源证据样本</span>
            <strong>{analysis.source_video.title}</strong>
          </div>
          <div>
            <span>原视频作者</span>
            <strong>{sourceAuthor || "未识别"}</strong>
          </div>
          <div>
            <span>输入类型</span>
            <strong>{analysis.source_video.input_type}</strong>
          </div>
          <div>
            <span>转写来源</span>
            <strong>{analysis.transcript.source}</strong>
          </div>
          <div>
            <span>置信度</span>
            <strong>{Math.round(analysis.transcript.confidence * 100)}%</strong>
          </div>
          <RiskBadge level={analysis.risk_check.level} />
        </div>
        <details className="source-evidence-disclosure">
          <summary>查看即将写入 Skill 的来源证据</summary>
          <div className="source-evidence-grid">
            <span>原视频作者</span>
            <strong>{sourceAuthor || "未识别"}</strong>
            <span>原视频链接</span>
            {sourceUrl ? (
              <a href={sourceUrl} target="_blank" rel="noreferrer">
                <ExternalLink size={14} />
                {sourceUrl}
              </a>
            ) : (
              <strong>未保存链接</strong>
            )}
            <span>原视频提取文稿</span>
            <p>{draft.source_transcript || analysis.transcript.content_text}</p>
          </div>
        </details>
      </Card>

      {!savedSkill ? (
        <div className="analysis-next-step wide-card" role="status">
          <div>
            <span>当前任务还剩 1 步</span>
            <strong>确认这是哪种结构能力，然后保存到 Skill 库</strong>
          </div>
          <span>保存后本次沉淀结束，不会自动进入文稿生成。</span>
        </div>
      ) : null}

      <Card className="wide-card">
        <SectionHeader
          title="结构能力拆解"
          description="这里回答运营最关心的问题：这套文本结构为什么值得沉淀，后面怎么跨题材复用。"
          action={<RiskBadge level={analysis.risk_check.level} />}
        />
        <div className="writing-dissection-grid">
          <div>
            <span>开头结构亮点</span>
            <strong>{analysis.analysis.hook}</strong>
          </div>
          <div>
            <span>中段推进方式</span>
            <strong>{analysis.analysis.conflict}</strong>
          </div>
          <div>
            <span>情绪节奏</span>
            <strong>{analysis.analysis.emotion_curve.join(" -> ")}</strong>
          </div>
          <div>
            <span>结尾复用方式</span>
            <strong>{analysis.analysis.ending_cta}</strong>
          </div>
        </div>
      </Card>

      <Card className="wide-card">
        <SectionHeader
          title="可迁移写法"
          description="只沉淀可跨题材复用的结构动作，不逐句仿写原视频。"
        />
        <div className="borrow-list">
          {(draft.borrowable_moves.length
            ? draft.borrowable_moves
            : analysis.analysis.template_suggestions
          ).map((item) => (
            <div key={item}>
              <Sparkles size={16} />
              <span>{item}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card className="wide-card">
        <SectionHeader
          title={savedSkill ? "Skill 已保存" : "确认可复用写作能力"}
          description={
            savedSkill
              ? savedSkill.status === "active"
                ? "该 Skill 已通过发布门禁；确认本次团队同步后，可手动发布到 GitHub。"
                : `已保存为候选 Skill，当前来源 ${savedSkill.source_count || 1}/3；继续沉淀同一结构的视频时，选择它作为归属即可补齐证据。`
              : "AI 生成的是结构能力草稿。确认能力名、适用题材和复用边界后，才会进入 Skill 库。"
          }
        />
        {savedSkill ? (
          <div className="skill-save-success" role="status">
            <CheckCircle2 size={28} />
            <div>
              <span>已加入 Skill 库</span>
              <strong>{savedSkill.name}</strong>
              <p>
                {savedSkill.status !== "active"
                  ? `候选进度：${savedSkill.source_count || 1}/3 个授权来源。正式包不会加载候选；它可继续积累证据。`
                  : skillPack
                  ? `站内同步包已生成：${skillPack.skill_name}@${skillPack.version}，包含 ${skillPack.active_skill_count} 个启用 Skill。`
                  : "站内已保存，发布到 GitHub 后团队成员再更新本地 Skill 包即可复用。"}
              </p>
            </div>
            <div className="skill-save-actions">
              <button
                type="button"
                className="primary-button"
                onClick={onStartAnother}
              >
                <PlusCircle size={16} />
                继续沉淀视频
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={onOpenSkillLibrary}
              >
                <Library size={16} />
                查看团队 Skill 库
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={onPublishSkillPack}
                disabled={skillPublishing || savedSkill.status !== "active"}
              >
                <UploadCloud size={16} />
                {skillPublishing ? "发布中..." : "发布到 GitHub"}
              </button>
            </div>
            {skillPublishResult ? (
              <div className="skill-publish-status" role="status">
                <CheckCircle2 size={16} />
                <span>
                  {skillPublishResult.status === "published"
                    ? `已发布 ${skillPublishResult.files_changed} 个文件`
                    : "GitHub 已是最新版"}
                  {skillPublishResult.commit_sha
                    ? `，提交 ${skillPublishResult.commit_sha.slice(0, 7)}`
                    : ""}
                </span>
              </div>
            ) : null}
            {skillPublishError ? (
              <div className="alert-box alert-warning">
                <strong>GitHub 发布失败</strong>
                <span>{skillPublishError}</span>
              </div>
            ) : null}
          </div>
        ) : null}
        {!savedSkill ? (
          <div className="skill-duplicate-notice" role="status">
            <GitMerge size={18} />
            <div>
              <strong>
                {mergeTarget
                  ? `本次会作为「${mergeTarget.name}」的第 ${(mergeTarget.source_count || 0) + 1}/3 个来源`
                  : "本次将创建新的候选 Skill"}
              </strong>
              <span>
                选择归属由你决定；系统只提供相似结构建议，不会在后台替你猜。
              </span>
            </div>
          </div>
        ) : null}
        {!savedSkill ? (
          <div className="preset-summary-card">
            <div>
              <span className="eyebrow-text">结构能力名</span>
              <input
                aria-label="结构能力名"
                className="text-input"
                value={draftForm?.name || ""}
                onChange={(event) =>
                  setDraftForm((current) =>
                    current
                      ? { ...current, name: event.target.value }
                      : current,
                  )
                }
              />
              <small className="field-hint">
                只描述写法，不写原视频主题、人物或价值观。例如：命题钩子·多例递进。
              </small>
            </div>
            <label>
              <span>来源归属</span>
              <select
                className="text-input"
                value={mergeTargetId}
                onChange={(event) => setMergeTargetId(event.target.value)}
              >
                <option value="new">创建新的候选 Skill</option>
                {mergeCandidates.map((template) => (
                  <option key={template.id} value={template.id}>
                    补充「{template.name}」 ({template.source_count || 0}/3)
                  </option>
                ))}
              </select>
              <small className="field-hint">
                选择现有 Skill 会把本视频及其证据追加为下一条来源；创建新候选不会自动合并。
              </small>
            </label>
            <div className="chip-row">
              <Badge tone="accent">{draft.account_type}</Badge>
              {draft.hotspot_types.map((item) => (
                <Badge key={item}>{item}</Badge>
              ))}
            </div>
            <div>
              <span>它解决哪些写作问题</span>
              <div className="chip-row">
                {(draft.solves_problems || []).map((item) => (
                  <Badge key={item} tone="accent">
                    {item}
                  </Badge>
                ))}
              </div>
            </div>
            <div>
              <span>AI 辅助判断依据</span>
              <div className="chip-row">
                {skillMatchSignals(analysis).map((item) => (
                  <Badge key={item}>{item}</Badge>
                ))}
              </div>
            </div>
            <div>
              <span>可迁移结构骨架</span>
              <textarea
                aria-label="可迁移结构骨架"
                className="text-area compact-area"
                value={draftForm?.skeleton || ""}
                onChange={(event) =>
                  setDraftForm((current) =>
                    current
                      ? { ...current, skeleton: event.target.value }
                      : current,
                  )
                }
              />
            </div>
            <div>
              <span>开头公式</span>
              <strong>{draft.hook_formula}</strong>
            </div>
            <div>
              <span>情绪节奏</span>
              <strong>{draft.emotion_rhythm}</strong>
            </div>
            <div>
              <span>结构适用条件</span>
              <textarea
                aria-label="结构适用条件"
                className="text-area compact-area"
                value={draftForm?.applicableScenes || ""}
                onChange={(event) =>
                  setDraftForm((current) =>
                    current
                      ? { ...current, applicableScenes: event.target.value }
                      : current,
                  )
                }
              />
            </div>
            <div>
              <span>复用边界</span>
              <textarea
                aria-label="复用边界"
                className="text-area compact-area"
                value={draftForm?.unsuitableScenes || ""}
                onChange={(event) =>
                  setDraftForm((current) =>
                    current
                      ? { ...current, unsuitableScenes: event.target.value }
                      : current,
                  )
                }
              />
            </div>
            <div className="detail-warning">
              <span>使用边界</span>
              <strong>{draft.risk_boundary}</strong>
            </div>
          </div>
        ) : null}
        {!savedSkill ? (
          <button
            type="button"
            className="primary-button wide-button animated-action"
            onClick={() => onSavePreset(savePayload)}
            disabled={savingPreset}
          >
            {mergeTarget ? (
              <GitMerge size={16} />
            ) : (
              <Archive size={16} />
            )}
            {savingPreset
              ? "保存中..."
              : mergeTarget
                ? `补充为第 ${(mergeTarget.source_count || 0) + 1}/3 个来源`
                : "保存为写作 Skill"}
          </button>
        ) : null}
      </Card>

      <Card className="wide-card">
        <SectionHeader
          title="风险诊断"
          description="默认检查隐私、谣言、人身攻击、恶意引战和高敏表达。"
          action={<RiskBadge level={analysis.risk_check.level} />}
        />
        <div className="risk-list">
          {analysis.risk_check.items.map((item) => (
            <div key={item.label}>
              <strong>{item.label}</strong>
              <span>{item.reason}</span>
              <p>{item.rewrite}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
