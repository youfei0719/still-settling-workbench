import {
  AlertCircle,
  Check,
  ChevronDown,
  FileAudio,
  FileCheck2,
  LoaderCircle,
  Link2,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import type { DepositSession, SourceMode, TranscriptProofreadResult } from "./types"

const stageCopy = {
  source: { title: "识别授权来源", idle: "等待输入可验证来源" },
  transcript: { title: "提取真实稿件", idle: "没有真实稿件前不拆解" },
  proofread: { title: "AI 校对并确认稿件", idle: "等待真实稿件" },
  structure: { title: "拆解写作结构", idle: "等待真实稿件" },
  save: { title: "自动建立候选并评测", idle: "等待结构拆解完成" },
}

function Step({
  title,
  detail,
  state,
  children,
}: {
  title: string
  detail: string
  state: "done" | "blocked" | "waiting" | "ready" | "active"
  children?: React.ReactNode
}) {
  return (
    <details className={`deposit-step is-${state}`} open={state === "blocked" || state === "ready" || state === "active"}>
      <summary>
        <span className="step-indicator">
          {state === "done" ? <Check size={13} /> : state === "blocked" ? <AlertCircle size={13} /> : state === "active" ? <LoaderCircle size={13} className="spin" /> : <i />}
        </span>
        <div><strong>{title}</strong><small>{detail}</small></div>
        <em>{state === "done" ? "已完成" : state === "blocked" ? "已停止" : state === "active" ? "进行中" : state === "ready" ? "待确认" : "等待中"}</em>
        <ChevronDown size={14} />
      </summary>
      {children ? <div className="step-detail">{children}</div> : null}
    </details>
  )
}

function ProgressRail({ active }: { active: "media" | "proofread" | "structure" | null }) {
  const phases = [["media", "获取稿件"], ["proofread", "校对确认"], ["structure", "结构拆解"]] as const
  const activeIndex = phases.findIndex(([id]) => id === active)
  return <div className="workflow-rail" aria-live="polite">{phases.map(([id, label], index) => <div key={id} className={active === id ? "is-running" : activeIndex > index ? "is-complete" : ""}>
    <span>{activeIndex > index ? <Check size={11} /> : active === id ? <LoaderCircle size={11} className="spin" /> : index + 1}</span><small>{label}</small>
  </div>)}</div>
}

function ProofreadReview({ review, onConfirm }: { review: TranscriptProofreadResult; onConfirm: (transcript: string) => void }) {
  const [confirmed, setConfirmed] = useState(false)
  const [transcript, setTranscript] = useState(review.formattedTranscript)
  useEffect(() => { setConfirmed(false); setTranscript(review.formattedTranscript) }, [review])
  return <div className="proofread-review">
    <div className="proofread-heading"><div><strong>校对建议</strong><small>{review.corrections.length ? `识别到 ${review.corrections.length} 处可确认修改` : "未发现可确认修改，已按语义分段"}</small></div><span>{review.provider}</span></div>
    <label className="proofread-transcript"><span>建议稿，可继续手动编辑自然段</span><textarea aria-label="AI 校对建议稿" rows={11} value={transcript} onChange={(event) => { setConfirmed(false); setTranscript(event.target.value) }} /></label>
    {review.corrections.length ? <div className="correction-list">{review.corrections.map((item) => <article key={item.id}><div className="correction-diff"><del>{item.original}</del><span>→</span><ins>{item.replacement}</ins></div><p>{item.reason} <b>{item.confidence}%</b></p></article>)}</div> : null}
    {review.uncertainties.length ? <div className="uncertainty-list"><strong>仍需人工确认</strong>{review.uncertainties.map((item, index) => <p key={`${item}-${index}`}>{item}</p>)}</div> : null}
    <label className="proofread-confirmation"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} /><span><strong>我已核对 AI 修改、段落和仍需确认项</strong><small>确认后这份稿件才会成为结构拆解的唯一输入。</small></span></label>
    <button type="button" className="primary-command" disabled={!confirmed || transcript.trim().length < 40} onClick={() => onConfirm(transcript)}><Check size={15} />确认校对稿并进入拆解</button>
  </div>
}

export function DepositPage({
  session,
  notice,
  processing,
  progressMessage,
  proofreading,
  analyzing,
  onRecognizeLink,
  onImportMedia,
  onUseTranscript,
  onUpdateTranscript,
  onProofread,
  onFinalizeProofread,
  onReset,
}: {
  session: DepositSession
  notice: string | null
  processing: boolean
  progressMessage: string | null
  proofreading: boolean
  analyzing: boolean
  onRecognizeLink: (value: string) => void
  onImportMedia: (file?: File) => void
  onUseTranscript: (transcript: string, sourceLabel: string) => void | Promise<void>
  onUpdateTranscript: (transcript: string) => void
  onProofread: () => void
  onFinalizeProofread: (transcript: string) => void
  onReset: () => void
}) {
  const [mode, setMode] = useState<SourceMode>("douyin_link")
  const [link, setLink] = useState("")
  const [transcript, setTranscript] = useState("")
  const [sourceLabel, setSourceLabel] = useState("")
  const [authorized, setAuthorized] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const stage = session.stage
  const sourceDone = stage !== "awaiting_source"
  const transcriptDone = ["transcript_ready", "proofread_ready", "structure_ready", "candidate_saved"].includes(stage)
  const proofreadDone = ["proofread_ready", "structure_ready", "candidate_saved"].includes(stage)
  const structureDone = ["structure_ready", "candidate_saved"].includes(stage)
  const hasProofreadRecord = Boolean(session.proofread)
  const sourceDescription = useMemo(
    () => session.source
      ? `${session.source.label} · ${session.source.mediaLocalOnly ? "媒体仅留本机" : "已记录来源"}`
      : stageCopy.source.idle,
    [session.source],
  )
  const activeProcess = processing ? "media" : proofreading ? "proofread" : analyzing ? "structure" : null

  const selectLocalMedia = () => {
    if ("__TAURI_INTERNALS__" in window || window.location.protocol === "tauri:") onImportMedia()
    else fileRef.current?.click()
  }

  return (
    <section className="deposit-page">
      {notice ? <div className="inline-notice" role="status"><AlertCircle size={15} />{notice}</div> : null}
      {processing && progressMessage ? <div className="inline-notice is-processing" role="status"><Sparkles size={15} />{progressMessage}</div> : null}
      <div className="deposit-grid">
        <section className="work-panel source-panel">
          <header>
            <div><h1>沉淀写作 Skill</h1><p>先取得经授权、可验证的真实稿件，再提炼可跨题材复用的写法结构。</p></div>
            {sourceDone ? <button type="button" className="text-button" onClick={onReset}>新建沉淀</button> : null}
          </header>
          <ProgressRail active={activeProcess} />
          <div className="source-modes" aria-label="来源方式">
            <button type="button" className={mode === "douyin_link" ? "is-active" : ""} onClick={() => setMode("douyin_link")}><Link2 size={14} />抖音分享链接</button>
            <button type="button" className={mode === "local_media" ? "is-active" : ""} onClick={() => setMode("local_media")}><FileAudio size={14} />本机媒体</button>
            <button type="button" className={mode === "verified_transcript" ? "is-active" : ""} onClick={() => setMode("verified_transcript")}><FileCheck2 size={14} />真实稿件</button>
          </div>

          {mode === "douyin_link" ? (
            <div className="source-form">
              <label>抖音分享文案或短链<textarea aria-label="抖音分享文案或短链" rows={4} value={link} onChange={(event) => setLink(event.target.value)} /></label>
              <button type="button" className="primary-command" disabled={!link.trim() || processing} onClick={() => onRecognizeLink(link)}><Link2 size={15} />{processing ? "真实媒体处理中..." : "开始提取并转写"}</button>
            </div>
          ) : null}

          {mode === "local_media" ? (
            <div className="local-import">
              <input ref={fileRef} type="file" hidden accept="video/*,audio/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) onImportMedia(file) }} />
              <button type="button" disabled={processing} onClick={selectLocalMedia}><Upload size={20} /><strong>选择本机视频或音频</strong><span>文件只交给本机 FFmpeg 与所选转写后端，完成后清理临时音频。</span></button>
              <p><LockKeyhole size={13} />原始媒体、临时音频和模型文件不会进入候选或发布包。</p>
            </div>
          ) : null}

          {mode === "verified_transcript" ? (
            <div className="transcript-input">
              <label>来源名称或链接<input aria-label="来源名称或链接" value={sourceLabel} onChange={(event) => setSourceLabel(event.target.value)} placeholder="用于识别本条授权稿件" /></label>
              <label>经授权的真实稿件<textarea aria-label="经授权的真实稿件" rows={9} value={transcript} onChange={(event) => setTranscript(event.target.value)} placeholder="粘贴完整、可追溯的真实稿件。这里不是补写标题或摘要的入口。" /></label>
              <label className="authorization-check">
                <input type="checkbox" checked={authorized} onChange={(event) => setAuthorized(event.target.checked)} />
                <span><strong>我确认这是真实稿件且来源已获授权</strong><small>系统会记录来源指纹，避免同一稿件被重复保存。</small></span>
              </label>
              <button type="button" className="primary-command" disabled={!authorized || sourceLabel.trim().length < 3 || transcript.trim().length < 40} onClick={() => onUseTranscript(transcript, sourceLabel)}><ShieldCheck size={15} />确认真实稿件</button>
            </div>
          ) : null}

          {stage === "transcript_blocked" ? (
            <div className="boundary-alert is-danger"><AlertCircle size={16} /><div><strong>本次停止拆解</strong><p>来源已经识别，但当前没有可验证的真实稿件。系统不会用标题、描述或手写摘要伪装分析。</p></div></div>
          ) : (
            <div className="boundary-alert"><ShieldCheck size={16} /><div><strong>真实性门禁</strong><p>没有真实稿件就不会进入结构拆解；每条稿件独立沉淀为一个 Skill。</p></div></div>
          )}
        </section>

        <section className="work-panel progress-panel">
          <header><h2>沉淀进度</h2><p>每一步都保留输入、证据状态和阻断原因。</p></header>
          <div className="step-list">
            <Step title={stageCopy.source.title} detail={sourceDescription} state={sourceDone ? "done" : "waiting"}>
              {session.source ? <p>来源类型：{session.source.mode === "douyin_link" ? "抖音分享链接" : session.source.mode === "local_media" ? "本机媒体" : "已验证稿件"}<br />授权状态：{session.source.authorized ? "已确认" : "待核验"}</p> : null}
            </Step>
            <Step title={stageCopy.transcript.title} detail={stage === "transcript_blocked" ? "未取得真实稿件，流程已停止" : transcriptDone ? `已取得 ${session.transcript.replace(/\s/g, "").length} 字真实稿件` : processing ? (progressMessage ?? "正在获取真实稿件") : stageCopy.transcript.idle} state={stage === "transcript_blocked" ? "blocked" : processing ? "active" : transcriptDone ? "done" : sourceDone ? "ready" : "waiting"}>
              {transcriptDone ? <label className="transcript-editor"><span>真实稿件，可先手动整理段落</span><textarea aria-label="提取真实稿件" rows={12} value={session.transcript} disabled={proofreadDone || structureDone} onChange={(event) => onUpdateTranscript(event.target.value)} /></label> : stage === "source_verified" ? <p>来源已校验，正在等待真实下载、音频提取和转写结果；失败时会停在本步骤。</p> : null}
            </Step>
            <Step title={stageCopy.proofread.title} detail={proofreadDone && hasProofreadRecord ? "校对稿已由人工确认" : structureDone ? "历史结构稿，未记录校对建议" : proofreading ? "正在分析错别字、语义和段落" : session.proofread ? "请逐项确认校对建议" : transcriptDone ? "真实稿件已就绪，需先经 AI 校对" : stageCopy.proofread.idle} state={proofreadDone || structureDone ? "done" : proofreading ? "active" : session.proofread || transcriptDone ? "ready" : "waiting"}>
              {transcriptDone && !proofreadDone && !session.proofread ? <button type="button" className="secondary-command" disabled={proofreading} onClick={onProofread}><Sparkles size={14} />{proofreading ? "AI 正在校对..." : "重新运行 AI 校对"}</button> : session.proofread && !proofreadDone ? <ProofreadReview review={session.proofread} onConfirm={onFinalizeProofread} /> : null}
            </Step>
            <Step title={stageCopy.structure.title} detail={structureDone ? "已从样本抽象为跨题材写作机制" : analyzing ? "正在根据已确认稿件拆解" : proofreadDone ? "正在准备结构拆解" : stageCopy.structure.idle} state={structureDone ? "done" : analyzing ? "active" : proofreadDone ? "active" : "waiting"}>
              {proofreadDone && !structureDone ? <p>{analyzing ? "模型正在自动拆解已确认稿件。" : "正在准备结构拆解。"}</p> : session.draft ? <p>{session.draft.purpose}</p> : null}
            </Step>
            <Step title={stageCopy.save.title} detail={stage === "candidate_saved" ? "候选已建立，模型评测会自动完成" : structureDone ? "正在建立候选并提交模型评测" : stageCopy.save.idle} state={stage === "candidate_saved" ? "done" : structureDone ? "active" : "waiting"}>
              {stage === "candidate_saved" ? <p>候选已保存在本机 Skill 库。评测通过后，只需进行一次最终发布确认。</p> : null}
            </Step>
          </div>
        </section>

        <section className="work-panel result-panel">
          <header><h2>可复用写作能力</h2><p>主产出是团队以后能复用的文本结构，不是本次视频摘要。</p></header>
          {session.draft ? (
            <div className="draft-preview">
              <div className="draft-heading"><span><Sparkles size={15} /></span><div><strong>{session.draft.name}</strong><small>{stage === "candidate_saved" ? "已自动建立候选并进入评测" : "正在自动建立候选"} · 本次来源 1 份</small></div></div>
              <div className="draft-readonly">
                <section><span>解决什么问题</span><p>{session.draft.purpose}</p></section>
                <section><span>开头</span><p>{session.draft.hook}</p></section>
                <section><span>推进</span><p>{session.draft.progression}</p></section>
                <section><span>收束</span><p>{session.draft.ending}</p></section>
                <section className="risk-section"><span>风险边界</span><p>{session.draft.riskBoundary}</p></section>
              </div>
            </div>
          ) : (
            <div className="result-empty"><FileCheck2 size={26} /><strong>还没有 Skill 草稿</strong><p>真实稿件准备完成后，系统会拆解文本结构、可借鉴写法和复用边界。</p></div>
          )}
        </section>
      </div>
    </section>
  )
}
