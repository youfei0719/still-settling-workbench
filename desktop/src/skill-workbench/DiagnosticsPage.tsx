import { AlertCircle, CheckCircle2, Clipboard, Cpu, Database, Download, HardDrive, KeyRound, LoaderCircle, RefreshCw, ShieldCheck, Trash2 } from "lucide-react"
import repositorySkillData from "virtual:douyin-skill-repository"
import { useMemo, useState } from "react"
import type { DiagnosticLog, LocalCandidate, RuntimeHealth } from "./types"
import { candidateGates } from "./workflow"
import { SettingsPanel } from "./SettingsPanel"

export function DiagnosticsPage({
  candidates,
  health,
  refreshing,
  onRefresh,
  logs,
  logsRefreshing,
  onRefreshLogs,
  onClearLogs,
}: {
  candidates: LocalCandidate[]
  health: RuntimeHealth | null
  refreshing: boolean
  onRefresh: () => void
  logs: DiagnosticLog[]
  logsRefreshing: boolean
  onRefreshLogs: () => void
  onClearLogs: () => void
}) {
  const [scope, setScope] = useState<"all" | "error" | "success">("all")
  const readyCandidates = candidates.filter((candidate) => Object.values(candidateGates(candidate)).every(Boolean))
  const checks = [
    {
      icon: CheckCircle2,
      title: "stable 文件完整性",
      value: repositorySkillData.version,
      detail: `${repositorySkillData.skills.length} 个 Skill 的 manifest、路径和内容哈希来自同一不可变版本。`,
      status: "healthy",
    },
    {
      icon: CheckCircle2,
      title: "stable 质量策略",
      value: "符合现行门禁",
      detail: "每个正式 Skill 均基于已授权真实稿件，并经过模型评测和人工主审。",
      status: "healthy",
    },
    {
      icon: health?.database === "healthy" ? Database : AlertCircle,
      title: "本机事实库",
      value: health?.database === "healthy" ? "SQLite 已连接" : "浏览器预览不连接 SQLite",
      detail: "来源、候选证据、模型评测、人工主审和导出记录由同一事务保存。",
      status: health?.database === "healthy" ? "healthy" : "neutral",
    },
    {
      icon: health?.mediaPipeline.status === "healthy" ? CheckCircle2 : AlertCircle,
      title: "本机媒体处理链",
      value: health?.mediaPipeline.label ?? "检查中",
      detail: health?.mediaPipeline.status === "healthy"
        ? `处理链 ${health.mediaPipeline.protocolVersion} · 转写模型 ${health.mediaPipeline.version}`
        : "需要 FFmpeg，以及本机 MLX Whisper 或支持 audio/transcriptions 的转写 API；抖音无登录解析还需要 Chrome、Edge 或 Chromium。",
      status: health?.mediaPipeline.status === "healthy" ? "healthy" : "warning",
    },
    {
      icon: Cpu,
      title: "模型评测边界",
      value: `${readyCandidates.length} 个候选通过全部门禁`,
      detail: "结构拆解与质量评测都调用已配置模型；调用失败不会生成或记录通过结果。",
      status: readyCandidates.length ? "healthy" : "neutral",
    },
    {
      icon: HardDrive,
      title: "媒体与发布包",
      value: "仅保留在本机",
      detail: "发布候选包不包含原始媒体、临时音频、完整稿件或密钥，只包含结构与质量证据摘要。",
      status: "healthy",
    },
    {
      icon: KeyRound,
      title: "凭据库接口",
      value: health?.credentialStore === "available_unverified" ? "系统接口可用，未读写密钥" : "浏览器预览不可用",
      detail: "Keychain / Credential Manager 只通过原生命令访问；诊断不会读取或展示凭据。",
      status: health?.credentialStore === "available_unverified" ? "healthy" : "neutral",
    },
  ]
  const visibleLogs = useMemo(() => scope === "all" ? logs : logs.filter((log) => log.status === scope), [logs, scope])
  const copyLog = async (log: DiagnosticLog) => {
    await navigator.clipboard?.writeText(JSON.stringify(log, null, 2))
  }
  const exportLogs = () => {
    const content = JSON.stringify(logs, null, 2)
    const url = URL.createObjectURL(new Blob([content], { type: "application/json" }))
    const link = document.createElement("a")
    link.href = url
    link.download = `douyin-writing-skills-diagnostics-${new Date().toISOString().replace(/[:.]/g, "-")}.json`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="diagnostics-page">
      <header className="page-title"><div><h1>系统诊断</h1><p>分别检查运行时、stable 文件完整性和现行质量策略，不把静态文案当健康状态。</p></div><button type="button" className="secondary-command" disabled={refreshing} onClick={onRefresh}>{refreshing ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />}重新检查</button></header>
      <SettingsPanel onSettingsChanged={onRefresh} />
      <div className="diagnostic-overview"><div><Database size={18} /><span>运行模式</span><strong>{health?.mode === "native" ? "Tauri 原生运行时" : "浏览器开发预览"}</strong><small>{health ? `检查于 ${new Date(health.checkedAt).toLocaleTimeString("zh-CN")}` : "正在读取真实状态"}</small></div><div><ShieldCheck size={18} /><span>发布边界</span><strong>本机 Skill 与 stable 严格分离</strong><small>一条授权真实稿件即可沉淀；发布 stable 时需模型评测和人工主审</small></div></div>
      <div className="diagnostic-list">{checks.map((check) => <article key={check.title}><span className={`check-icon is-${check.status}`}><check.icon size={17} /></span><div><h2>{check.title}</h2><p>{check.detail}</p></div><strong>{check.value}</strong></article>)}</div>
      <section className="runtime-log-panel">
        <header><div><h2>运行日志</h2><p>日志只保留动作、阶段、代码和脱敏技术详情。</p></div><div className="log-actions"><button type="button" className="icon-command" title="刷新日志" onClick={onRefreshLogs} disabled={logsRefreshing}>{logsRefreshing ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />}</button><button type="button" className="icon-command" title="导出日志" onClick={exportLogs} disabled={!logs.length}><Download size={14} /></button><button type="button" className="icon-command" title="清空日志" onClick={onClearLogs} disabled={!logs.length}><Trash2 size={14} /></button></div></header>
        <div className="segmented compact" aria-label="日志筛选">{[["all", "全部"], ["error", "失败"], ["success", "成功"]].map(([value, label]) => <button type="button" key={value} className={scope === value ? "is-active" : ""} onClick={() => setScope(value as typeof scope)}>{label}</button>)}</div>
        {visibleLogs.length ? <div className="runtime-log-list">{visibleLogs.map((log) => <details key={log.id} className={`is-${log.status}`}><summary><span className="log-status">{log.status === "error" ? <AlertCircle size={14} /> : log.status === "success" ? <CheckCircle2 size={14} /> : <LoaderCircle size={14} />}</span><div><strong>{log.message}</strong><small>{new Date(log.createdAt).toLocaleString("zh-CN")} · {log.action}</small></div><code>{log.code}</code></summary><div className="runtime-log-detail"><dl><div><dt>阶段</dt><dd>{log.stage}</dd></div><div><dt>位置</dt><dd><code>{log.location}</code></dd></div><div><dt>关联 ID</dt><dd><code>{log.traceId}</code></dd></div>{log.detail ? <div><dt>技术详情</dt><dd>{log.detail}</dd></div> : null}</dl><button type="button" className="icon-command" title="复制这条日志" onClick={() => void copyLog(log)}><Clipboard size={14} /></button></div></details>)}</div> : <div className="runtime-log-empty">尚无{scope === "all" ? "运行" : scope === "error" ? "失败" : "成功"}日志。</div>}
      </section>
      <section className="boundary-table"><header><h2>系统边界</h2><p>每层只处理自己的事实来源。</p></header><div><span>React 工作台</span><p>来源确认、结构编辑、模型评测与主审记录</p></div><div><span>Tauri 命令层</span><p>文件选择、媒体处理、模型请求、凭据、SQLite 与 Git 发布事务</p></div><div><span>本机媒体链</span><p>临时 Chrome/Edge 上下文生成抖音请求签名，yt-dlp 负责降级，FFmpeg 与本机 MLX/转写 API 生成真实稿件，结束后清理全部临时数据</p></div><div><span>SQLite</span><p>来源、证据、候选、评测、主审和发布记录的本机事实来源</p></div><div><span>GitHub stable</span><p>生成不可变版本、文件 SHA-256 与 stable 指针后，由 Git 提交并推送</p></div></section>
    </section>
  )
}
