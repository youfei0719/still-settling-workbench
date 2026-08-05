import {
  AlertCircle,
  BookOpen,
  Check,
  CheckCircle2,
  FileOutput,
  FileText,
  Search,
  ShieldCheck,
} from "lucide-react"
import { useMemo, useState } from "react"
import type { LocalCandidate, PublishProgress, PublishResult, StableRepositorySnapshot } from "./types"
import { candidateGates } from "./workflow"

const statusCopy = {
  collecting: "待整理",
  review_ready: "质量复核",
  release_ready: "可生成正式版本",
  exported: "发布候选已导出",
}

function CandidateWorkspace({
  candidate,
  onPublishConfirmed,
  onRetryExport,
  evaluating,
  remediating,
  publishing,
  publishProgress,
  publishJob,
}: {
  candidate: LocalCandidate
  onPublishConfirmed: (candidateId: string) => void
  onRetryExport: (candidateId: string) => void
  evaluating: boolean
  remediating: boolean
  publishing: boolean
  publishProgress: PublishProgress | null
  publishJob: PublishResult | null | undefined
}) {
  const [publishConfirmed, setPublishConfirmed] = useState(false)
  const gates = candidateGates(candidate)

  return (
    <details className="candidate-workspace">
      <summary>
        <div className="asset-status"><AlertCircle size={15} /><span>{statusCopy[candidate.status]}</span></div>
        <div><h3>{candidate.name}</h3><p>{candidate.purpose}</p><small>{candidate.sourceCount} 条已授权真实稿件 · 点击查看文稿与质量记录</small></div>
        <div className="candidate-gate-summary"><span className={gates.sources ? "is-done" : ""}>来源</span><span className={gates.model ? "is-done" : ""}>模型</span><span className={gates.human ? "is-done" : ""}>主审</span></div>
        <time>{new Date(candidate.updatedAt).toLocaleString("zh-CN")}</time>
      </summary>
      <div className="candidate-detail">
        <section className="gate-checklist" aria-label="发布门禁">
          <div className={gates.sources ? "is-done" : ""}>{gates.sources ? <Check size={14} /> : <span>1</span>}<strong>授权真实稿件</strong><small>{candidate.sourceCount} 条</small></div>
          <div className={gates.model ? "is-done" : ""}>{gates.model ? <Check size={14} /> : <span>2</span>}<strong>模型评测 ≥ 80</strong><small>{candidate.modelEvaluation ? `${candidate.modelEvaluation.score} 分 · ${candidate.modelEvaluation.status === "passed" ? "通过" : "未通过"}` : "未评测"}</small></div>
          <div className={gates.human ? "is-done" : ""}>{gates.human ? <Check size={14} /> : <span>3</span>}<strong>最终发布确认</strong><small>{candidate.humanReview ? "已确认" : "待确认"}</small></div>
        </section>

        <section className="evidence-section">
          <header><div><h4>沉淀来源</h4><p>每个 Skill 可由一条已授权真实稿件独立沉淀；额外稿件仅用于后续迭代。</p></div></header>
          <div className="evidence-list">{candidate.sources.map((evidence, index) => <details key={evidence.id} className="evidence-record">
            <summary><strong>{index + 1}. {evidence.source.label}</strong><span>{evidence.source.mode === "verified_transcript" ? "授权稿件" : evidence.source.mode === "local_media" ? "本机媒体" : "抖音来源"}</span><code>{evidence.fingerprint}</code></summary>
            <div className="evidence-transcript-detail">
              <section><header><FileText size={15} /><div><h5>提取视频文稿</h5><p>{evidence.proofread ? "AI 校对前的原始提取稿，仅保留在本机证据库。" : "历史记录未保存校对前版本，以下为已确认的本机稿件。"}</p></div></header><pre>{evidence.proofread?.originalTranscript ?? evidence.transcript}</pre></section>
              <section><header><CheckCircle2 size={15} /><div><h5>确认后的文稿</h5><p>这份稿件是结构拆解的唯一输入，不会进入 stable 发布包。</p></div></header><pre>{evidence.transcript}</pre></section>
              {evidence.proofread ? <section><header><ShieldCheck size={15} /><div><h5>错别字与语义校对</h5><p>{evidence.proofread.provider} · {evidence.proofread.corrections.length ? `已记录 ${evidence.proofread.corrections.length} 处建议修改` : "未发现需要逐项确认的修改"}</p></div></header>
                {evidence.proofread.corrections.length ? <div className="correction-list">{evidence.proofread.corrections.map((item) => <article key={item.id}><div className="correction-diff"><del>{item.original}</del><span>→</span><ins>{item.replacement}</ins></div><p>{item.reason} <b>{item.confidence}%</b></p></article>)}</div> : null}
                {evidence.proofread.uncertainties.length ? <div className="uncertainty-list"><strong>仍需人工确认</strong>{evidence.proofread.uncertainties.map((item, uncertaintyIndex) => <p key={`${item}-${uncertaintyIndex}`}>{item}</p>)}</div> : null}
              </section> : null}
            </div>
          </details>)}</div>
        </section>

        {gates.sources ? (
          <section className="review-form">
            <header><CheckCircle2 size={16} /><div><h4>自动发布质量检查</h4><p>结构拆解后，系统会自动检查跨题材复用性；发现样本题材残留时会自动修正并复评。</p></div></header>
            {evaluating || remediating ? <div className="automatic-quality-status is-running"><span className="progress-dot" /><strong>{remediating ? "正在自动修正为通用写作机制" : "正在检查发布质量"}</strong><small>无需人工操作</small></div> : candidate.modelEvaluation ? <div className={`evaluation-result is-${candidate.modelEvaluation.status}`}><strong>{candidate.modelEvaluation.score} 分 · {candidate.modelEvaluation.status === "passed" ? "已达到发布标准" : "未达到发布标准"}</strong><span>{candidate.modelEvaluation.evaluator}</span><p>{candidate.modelEvaluation.status === "passed" ? "已完成自动抽象与质量检查，等待最终发布确认。" : "系统已完成自动修正尝试，但仍未达到发布标准。请重新沉淀或查看运行日志。"}</p></div> : <div className="automatic-quality-status is-running"><span className="progress-dot" /><strong>正在准备自动质量检查</strong><small>无需人工操作</small></div>}
          </section>
        ) : null}

        {gates.model && !gates.human ? (
          <section className="release-form">
            <header><FileOutput size={16} /><div><h4>确认发布 stable Skill</h4><p>系统会生成不可变版本、同步远端变更并推送到已配置的 GitHub 仓库。</p></div></header>
            <label className="review-confirmation"><input type="checkbox" checked={publishConfirmed} onChange={(event) => setPublishConfirmed(event.target.checked)} /><span><strong>我已确认通用 Skill 结构、模型评测和风险边界</strong><small>确认后立即生成并发布 stable Skill。</small></span></label>
            <button type="button" className="primary-command" disabled={!publishConfirmed || publishing} onClick={() => onPublishConfirmed(candidate.id)}><FileOutput size={14} />{publishing ? "正在生成并同步..." : "确认并发布 stable Skill"}</button>
            {publishing && publishProgress ? <PublishProgressRail progress={publishProgress} /> : null}
          </section>
        ) : null}

        {gates.human ? <section className="release-form">
          <header><FileOutput size={16} /><div><h4>{candidate.release ? "stable Skill 已发布" : "发布同步待完成"}</h4><p>{candidate.release ? "不可变版本已写入 stable 清单。" : "上次发布已创建本地提交，但远端同步尚未完成。"}</p></div></header>
          {candidate.release ? <div className="release-result"><CheckCircle2 size={15} /><div><strong>{candidate.release.version}</strong><code>{candidate.release.path}</code></div></div> : <><button type="button" className="primary-command" disabled={publishing} onClick={() => onRetryExport(candidate.id)}><FileOutput size={14} />{publishing ? "正在同步..." : "重试同步 stable Skill"}</button>{publishing && publishProgress ? <PublishProgressRail progress={publishProgress} /> : null}</>}
          {publishJob ? <div className="release-result"><FileOutput size={15} /><div><strong>{publishJob.version} · {publishJob.stage}</strong><code>{publishJob.commitSha ?? "尚未生成本地提交"}</code>{publishJob.commitUrl ? <a href={publishJob.commitUrl} target="_blank" rel="noreferrer">查看 GitHub commit</a> : null}<small>{publishJob.remoteVerifiedAt ? `远端已验证：${new Date(publishJob.remoteVerifiedAt).toLocaleString("zh-CN")}` : publishJob.errorMessage ?? "发布任务已保存在 SQLite，可重试同一版本。"}</small></div></div> : null}
        </section> : null}
      </div>
    </details>
  )
}

const publishStages: Array<{ id: PublishProgress["stage"]; label: string }> = [
  { id: "fetching", label: "同步仓库" },
  { id: "loading_base", label: "校验 stable" },
  { id: "building", label: "合并运行时" },
  { id: "validating", label: "校验发布包" },
  { id: "committing", label: "提交本地仓库" },
  { id: "pushing", label: "推送 GitHub" },
  { id: "verifying", label: "验证远端" },
]

function PublishProgressRail({ progress }: { progress: PublishProgress }) {
  const active = publishStages.findIndex((stage) => stage.id === progress.stage)
  const completed = progress.stage === "succeeded"
  return <div className="publish-progress" role="status" aria-live="polite"><div className="publish-progress-stages">{publishStages.map((stage, index) => <div key={stage.id} className={completed || index < active ? "is-complete" : index === active ? "is-active" : ""}><span>{completed || index < active ? <Check size={12} /> : index + 1}</span><small>{stage.label}</small></div>)}</div><p>{progress.message}</p></div>
}

export function LibraryPage({
  candidates,
  stableSnapshot,
  publishJobs,
  notice,
  onPublishConfirmed,
  onRetryExport,
  evaluatingCandidateId,
  remediatingCandidateId,
  publishingCandidateId,
  publishProgress,
}: {
  candidates: LocalCandidate[]
  stableSnapshot: StableRepositorySnapshot | null
  publishJobs: Record<string, PublishResult | null>
  notice: string | null
  onPublishConfirmed: (candidateId: string) => void
  onRetryExport: (candidateId: string) => void
  evaluatingCandidateId: string | null
  remediatingCandidateId: string | null
  publishingCandidateId: string | null
  publishProgress: PublishProgress | null
}) {
  const [search, setSearch] = useState("")
  const [scope, setScope] = useState<"all" | "stable" | "candidate">("all")
  const stable = useMemo(() => (stableSnapshot?.skills ?? []).filter((skill) => {
    const text = JSON.stringify(skill).toLocaleLowerCase()
    return !search || text.includes(search.toLocaleLowerCase())
  }), [search, stableSnapshot])
  const local = useMemo(() => candidates.filter((skill) => !search || `${skill.name} ${skill.purpose}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())), [candidates, search])

  return (
    <section className="library-page">
      <header className="page-title"><div><h1>写作 Skill 库</h1><p>候选自动完成结构评测；stable 仅显示 Tauri 已校验的目标仓库快照。</p></div><div className="stable-version"><CheckCircle2 size={15} /><span>{stableSnapshot?.verified ? "文件完整性" : "stable 状态"}</span><strong>{stableSnapshot?.version ?? "未连接"}</strong></div></header>
      {notice ? <div className="inline-notice" role="status"><AlertCircle size={15} />{notice}</div> : null}
      {!stableSnapshot?.verified ? <div className="inline-notice" role="status"><AlertCircle size={15} />{stableSnapshot?.error ?? "正在读取真实 stable repository snapshot"}</div> : null}
      <div className="library-toolbar"><label><Search size={15} /><input aria-label="搜索写作 Skill" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索名称、适用条件或解决问题" /></label><div className="segmented">{[["all", "全部"], ["stable", "稳定版本"], ["candidate", "本机候选"]].map(([value, label]) => <button key={value} type="button" className={scope === value ? "is-active" : ""} onClick={() => setScope(value as typeof scope)}>{label}</button>)}</div></div>
      <div className="library-summary"><div><BookOpen size={16} /><span>稳定能力</span><strong>{stable.length}</strong></div><div><FileText size={16} /><span>本机 Skill</span><strong>{candidates.length}</strong></div><p><ShieldCheck size={14} />{stableSnapshot?.repositoryPath ? `${stableSnapshot.remoteUrl || stableSnapshot.repositoryPath} · ${stableSnapshot.branch || "local"}` : "浏览器只读预览不伪造 stable 数据"}</p></div>

      {(scope === "all" || scope === "candidate") ? (
        <section className="skill-section"><header><div><h2>本机 Skill</h2><p>每条经确认稿件会自动建立、自动评测；通过后可直接确认发布 stable。</p></div><span>{local.length}</span></header>
          {local.length ? <div className="skill-asset-list">{local.map((candidate) => <CandidateWorkspace key={candidate.id} candidate={candidate} onPublishConfirmed={onPublishConfirmed} onRetryExport={onRetryExport} evaluating={evaluatingCandidateId === candidate.id} remediating={remediatingCandidateId === candidate.id} publishing={publishingCandidateId === candidate.id} publishProgress={publishingCandidateId === candidate.id ? publishProgress : null} publishJob={publishJobs[candidate.id]} />)}</div> : <div className="library-empty"><FileText size={22} /><strong>没有匹配的本机 Skill</strong></div>}
        </section>
      ) : null}

      {(scope === "all" || scope === "stable") ? (
        <section className="skill-section"><header><div><h2>稳定版本</h2><p>{stableSnapshot?.verified ? `已校验 ${stableSnapshot.packagePath} 的路径、大小和 SHA-256。` : "仅在原生运行时展示真实 stable 内容。"}</p></div><span>{stable.length}</span></header>{stable.length ? <div className="skill-asset-list">{stable.map((skill) => {
          const data = skill as Record<string, unknown>
          const name = typeof data.name === "string" ? data.name : "未命名 Skill"
          const tags = Array.isArray(data.hotspot_types) ? data.hotspot_types.filter((tag): tag is string => typeof tag === "string").slice(0, 3) : []
          return <details key={typeof data.id === "string" ? data.id : name} className="skill-asset stable"><summary><div className="asset-status"><CheckCircle2 size={15} /><span>stable</span></div><div><h3>{name}</h3><p>{typeof data.choose_when === "string" ? data.choose_when : ""}</p><small>{typeof data.account_type === "string" ? data.account_type : "团队 Skill"} · 质量分 {String(data.quality_score ?? "-")}</small></div><div className="asset-tags">{tags.map((tag) => <span key={tag}>{tag}</span>)}</div><time>{stableSnapshot?.updatedAt ? new Date(stableSnapshot.updatedAt).toLocaleDateString("zh-CN") : ""}</time></summary><div className="asset-detail"><section><span>写作方法</span><p>{typeof data.writing_method === "string" ? data.writing_method : ""}</p></section><section><span>风险边界</span><p>{typeof data.risk_boundary === "string" ? data.risk_boundary : ""}</p></section><code>{typeof data.reference_file === "string" ? data.reference_file : ""}</code></div></details>
        })}</div> : <div className="library-empty"><FileText size={22} /><strong>{stableSnapshot?.verified ? "当前 stable 尚未发布 Skill" : "未连接真实 stable repository"}</strong></div>}</section>
      ) : null}
    </section>
  )
}
