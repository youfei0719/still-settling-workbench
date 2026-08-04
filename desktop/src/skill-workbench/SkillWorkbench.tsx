import { useCallback, useEffect, useState } from "react"
import { DepositPage } from "./DepositPage"
import { DiagnosticsPage } from "./DiagnosticsPage"
import { LibraryPage } from "./LibraryPage"
import { preparePublishCandidate } from "./releasePack"
import { WorkbenchShell } from "./Shell"
import { skillWorkbenchBridge } from "./skillWorkbenchBridge"
import { useDesktopUpdater } from "./updater"
import { UpdatePrompt } from "./UpdatePrompt"
import type {
  DepositSession,
  DiagnosticLog,
  HumanReview,
  LocalCandidate,
  PublishProgress,
  PublishResult,
  RuntimeHealth,
  StableRepositorySnapshot,
  SourceRecord,
  WorkbenchPage,
} from "./types"
import {
  applyCandidateRemediation,
  applyModelStructure,
  createSourceSession,
  markCandidateExported,
  recordHumanReview,
  recordModelEvaluation,
  saveCandidateFromSession,
} from "./workflow"
import "./skill-workbench.css"

function formatTranscript(value: string) {
  const normalized = value.trim().replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n")
  if (normalized.includes("\n\n")) return normalized
  const sentences = normalized.match(/[^。！？!?；;]+[。！？!?；;]?/g) ?? [normalized]
  const paragraphs: string[] = []
  let current = ""
  for (const sentence of sentences) {
    const next = `${current}${sentence}`.trim()
    if (current && next.length > 120) {
      paragraphs.push(current)
      current = sentence.trim()
    } else {
      current = next
    }
  }
  if (current) paragraphs.push(current)
  return paragraphs.join("\n\n")
}

function emptySession(): DepositSession {
  return {
    stage: "awaiting_source",
    source: null,
    transcript: "",
    transcriptQuality: "unavailable",
    proofread: null,
    draft: null,
    events: [],
  }
}

export default function SkillWorkbench() {
  const [page, setPage] = useState<WorkbenchPage>("deposit")
  const [session, setSession] = useState<DepositSession>(() => emptySession())
  const [candidates, setCandidates] = useState<LocalCandidate[]>([])
  const [persistenceReady, setPersistenceReady] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [health, setHealth] = useState<RuntimeHealth | null>(null)
  const [stableSnapshot, setStableSnapshot] = useState<StableRepositorySnapshot | null>(null)
  const [healthRefreshing, setHealthRefreshing] = useState(false)
  const [mediaProcessing, setMediaProcessing] = useState(false)
  const [mediaProgress, setMediaProgress] = useState<string | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [proofreading, setProofreading] = useState(false)
  const [evaluatingCandidateId, setEvaluatingCandidateId] = useState<string | null>(null)
  const [remediatingCandidateId, setRemediatingCandidateId] = useState<string | null>(null)
  const [publishingCandidateId, setPublishingCandidateId] = useState<string | null>(null)
  const [publishProgress, setPublishProgress] = useState<PublishProgress | null>(null)
  const [publishJobs, setPublishJobs] = useState<Record<string, PublishResult | null>>({})
  const [diagnosticLogs, setDiagnosticLogs] = useState<DiagnosticLog[]>([])
  const [logsRefreshing, setLogsRefreshing] = useState(false)
  const [updatePromptDismissed, setUpdatePromptDismissed] = useState(false)
  const updater = useDesktopUpdater()

  const errorMessage = (error: unknown) => error instanceof Error ? error.message : String(error)

  const refreshDiagnosticLogs = useCallback(async () => {
    setLogsRefreshing(true)
    try {
      setDiagnosticLogs(await skillWorkbenchBridge.listDiagnosticLogs())
    } catch (error) {
      setNotice(`无法读取运行日志：${errorMessage(error)}`)
    } finally {
      setLogsRefreshing(false)
    }
  }, [])

  const recordUiLog = useCallback(async (log: Partial<DiagnosticLog>) => {
    try {
      const saved = await skillWorkbenchBridge.recordDiagnosticLog({
        traceId: `ui-${crypto.randomUUID()}`,
        ...log,
      })
      setDiagnosticLogs((current) => [saved, ...current.filter((item) => item.id !== saved.id)].slice(0, 100))
    } catch {
      // Diagnostic persistence must never interrupt the user's active workflow.
    }
  }, [])

  useEffect(() => {
    if (updater.status !== "error" || !updater.error) return
    void recordUiLog({ action: "desktop.updater", stage: "update", status: "error", code: "UPDATER_OPERATION_FAILED", message: "桌面端更新操作失败", location: "SkillWorkbench.tsx:updater", detail: null })
  }, [recordUiLog, updater.error, updater.status])

  useEffect(() => { setUpdatePromptDismissed(false) }, [updater.update?.version])

  useEffect(() => {
    skillWorkbenchBridge.load().then((saved) => {
      if (saved) {
        setSession({ ...saved.session, proofread: saved.session.proofread ?? null })
        setCandidates(saved.candidates ?? [])
      }
      setPersistenceReady(true)
    }).catch((error) => {
      setNotice(`无法读取本机状态：${String(error)}`)
      setPersistenceReady(true)
    })
  }, [])

  useEffect(() => {
    if (!candidates.length) return
    Promise.all(candidates.map(async (candidate) => [candidate.id, await skillWorkbenchBridge.latestPublishJob(candidate.id)] as const))
      .then((entries) => setPublishJobs(Object.fromEntries(entries)))
      .catch(() => undefined)
  }, [candidates])

  useEffect(() => {
    let dispose: (() => void) | undefined
    skillWorkbenchBridge.onPublishProgress((progress) => setPublishProgress(progress)).then((unlisten) => { dispose = unlisten })
    return () => dispose?.()
  }, [])

  useEffect(() => {
    if (!persistenceReady) return
    skillWorkbenchBridge.save({ session, candidates }).catch((error) => {
      setNotice(`本机保存失败：${String(error)}`)
    })
  }, [candidates, persistenceReady, session])

  const refreshHealth = useCallback(() => {
    setHealthRefreshing(true)
    Promise.all([skillWorkbenchBridge.runtimeHealth(), skillWorkbenchBridge.loadStableRepositorySnapshot()])
      .then(([runtime, snapshot]) => { setHealth(runtime); setStableSnapshot(snapshot) })
      .catch((error) => setNotice(`系统诊断失败：${String(error)}`))
      .finally(() => { setHealthRefreshing(false); void refreshDiagnosticLogs() })
  }, [refreshDiagnosticLogs])

  useEffect(() => refreshHealth(), [refreshHealth])
  useEffect(() => { void refreshDiagnosticLogs() }, [refreshDiagnosticLogs])

  useEffect(() => {
    let dispose: (() => void) | undefined
    skillWorkbenchBridge.onMediaProgress((progress) => setMediaProgress(progress.message)).then((unlisten) => { dispose = unlisten })
    return () => dispose?.()
  }, [])

  const useSource = (source: SourceRecord, stage: DepositSession["stage"], transcript = "") => {
    setNotice(null)
    setSession(createSourceSession(source, stage, transcript))
  }

  const requestProofread = async (transcript: string) => {
    if (!transcript.trim()) return
    setProofreading(true)
    setNotice(null)
    try {
      const review = await skillWorkbenchBridge.proofreadTranscript(transcript)
      setSession((current) => ({ ...current, transcriptQuality: "needs_review", proofread: review, draft: null }))
      setNotice(review.corrections.length ? `AI 已识别 ${review.corrections.length} 处可确认修改，请审核后继续。` : "AI 已完成语义校对和自然分段，请审核稿件后继续。")
    } catch (error) {
      setNotice(`文本校对失败：${errorMessage(error)}`)
    } finally {
      setProofreading(false)
      void refreshDiagnosticLogs()
    }
  }

  const recognizeLink = async (value: string) => {
    const match = value.match(/https?:\/\/(?:[a-z0-9-]+\.)?douyin\.com\/[^\s]+/i)
    if (!match) {
      setNotice("没有识别到有效的 douyin.com 分享链接，来源未记录。")
      void recordUiLog({ action: "source.douyin", stage: "validation", status: "error", code: "SOURCE_DOUYIN_URL_INVALID", message: "抖音链接未通过格式校验", location: "SkillWorkbench.tsx:recognizeLink", detail: "输入内容中没有可用的 douyin.com 链接。" })
      return
    }
    const source: SourceRecord = {
      id: `source-${crypto.randomUUID()}`,
      mode: "douyin_link",
      label: "抖音分享来源",
      value: match[0],
      authorized: true,
      mediaLocalOnly: false,
      createdAt: new Date().toISOString(),
    }
    useSource(source, "source_verified")
    void recordUiLog({ action: "source.douyin", stage: "validation", status: "success", code: "SOURCE_DOUYIN_URL_ACCEPTED", message: "抖音分享链接已通过前端格式校验", location: "SkillWorkbench.tsx:recognizeLink", detail: null })
    setMediaProcessing(true)
    setMediaProgress("正在校验抖音来源")
    try {
      const result = await skillWorkbenchBridge.processMedia("douyin_link", value)
      const transcript = formatTranscript(result.transcript)
      useSource({ ...source, label: result.author ? `${result.title} · ${result.author}` : result.title, value: result.url ?? source.value }, "transcript_ready", transcript)
      setMediaProgress("真实稿件已取得，正在进行 AI 校对")
      await requestProofread(transcript)
    } catch (error) {
      useSource(source, "transcript_blocked")
      setNotice(`真实稿件获取失败：${errorMessage(error)}`)
    } finally {
      setMediaProcessing(false)
      setMediaProgress(null)
      void refreshDiagnosticLogs()
    }
  }

  const importMedia = async (file?: File) => {
    try {
      const source = await skillWorkbenchBridge.selectLocalMedia(file)
      if (!source) return
      useSource(source, "source_verified")
      void recordUiLog({ action: "source.local_media", stage: "selection", status: "success", code: "SOURCE_LOCAL_MEDIA_SELECTED", message: "本机媒体已选择", location: "SkillWorkbench.tsx:importMedia", detail: "文件路径仅用于本机处理，不写入运行日志。" })
      setMediaProcessing(true)
      setMediaProgress("正在校验本机媒体")
      const result = await skillWorkbenchBridge.processMedia("local_media", source.value)
      const transcript = formatTranscript(result.transcript)
      useSource({ ...source, label: result.title }, "transcript_ready", transcript)
      setMediaProgress("真实稿件已取得，正在进行 AI 校对")
      await requestProofread(transcript)
    } catch (error) {
      setSession((current) => current.source ? { ...current, stage: "transcript_blocked" } : current)
      setNotice(`媒体导入或转写失败：${errorMessage(error)}`)
      void recordUiLog({ action: "source.local_media", stage: "selection", status: "error", code: "SOURCE_LOCAL_MEDIA_FAILED", message: "本机媒体导入或转写失败", location: "SkillWorkbench.tsx:importMedia", detail: errorMessage(error) })
    } finally {
      setMediaProcessing(false)
      setMediaProgress(null)
      void refreshDiagnosticLogs()
    }
  }

  const useTranscript = async (transcript: string, sourceLabel: string) => {
    const formattedTranscript = formatTranscript(transcript)
    useSource({
      id: `source-${crypto.randomUUID()}`,
      mode: "verified_transcript",
      label: sourceLabel.trim(),
      value: sourceLabel.trim(),
      authorized: true,
      mediaLocalOnly: false,
      createdAt: new Date().toISOString(),
    }, "transcript_ready", formattedTranscript)
    void recordUiLog({ action: "source.verified_transcript", stage: "confirmation", status: "success", code: "SOURCE_TRANSCRIPT_CONFIRMED", message: "经授权真实稿件已确认", location: "SkillWorkbench.tsx:useTranscript", detail: `仅记录文本长度：${transcript.trim().length} 字。` })
    setNotice("真实稿件已确认，正在自动进行 AI 校对。")
    await requestProofread(formattedTranscript)
  }

  const updateTranscript = (transcript: string) => {
    setSession((current) => ({
      ...current,
      stage: "transcript_ready",
      transcript,
      transcriptQuality: "needs_review",
      proofread: null,
      draft: null,
    }))
  }

  const proofread = async () => {
    await requestProofread(session.transcript)
  }

  const finalizeProofread = (transcript: string) => {
    const confirmedTranscript = transcript.trim()
    const source = session.source
    setSession((current) => ({
      ...current,
      transcript: confirmedTranscript,
      transcriptQuality: "verified",
      stage: "proofread_ready",
      draft: null,
    }))
    setNotice("校对稿已确认，正在自动拆解写作结构。")
    void recordUiLog({ action: "transcript.proofread", stage: "human_confirmation", status: "success", code: "TRANSCRIPT_PROOFREAD_CONFIRMED", message: "AI 校对稿已由人工确认", location: "SkillWorkbench.tsx:finalizeProofread", detail: `仅记录确认稿长度：${transcript.trim().length} 字。` })
    void analyze(confirmedTranscript, source)
  }

  const analyze = async (transcript = session.transcript, source = session.source) => {
    if (!source || !transcript.trim()) return
    setAnalyzing(true)
    setNotice(null)
    try {
      const draft = await skillWorkbenchBridge.analyzeTranscript({
        title: source.label,
        transcript,
        sourceUrl: source.value,
      })
      const structured = applyModelStructure({
        ...session,
        source,
        transcript,
        transcriptQuality: "verified",
        stage: "proofread_ready",
        draft: null,
      }, draft)
      const saved = saveCandidateFromSession(structured)
      if (!saved.ok) throw new Error(saved.message)
      setCandidates((current) => [saved.candidate, ...current])
      setSession(saved.session)
      setNotice("已从样本中抽象出通用写作 Skill，正在自动运行质量评测。")
      void recordUiLog({ action: "candidate.create", stage: "automatic", status: "success", code: "SKILL_DRAFT_CREATED", message: "通用写作 Skill 草稿已自动建立", location: "SkillWorkbench.tsx:analyze", detail: "来源仅作为写法样本；已进入自动质量评测。" })
      void runModelEvaluation(saved.candidate.id, saved.candidate)
    } catch (error) {
      setNotice(`结构拆解失败：${errorMessage(error)}`)
    } finally {
      setAnalyzing(false)
      void refreshDiagnosticLogs()
    }
  }

  const updateCandidate = (candidateId: string, update: (candidate: LocalCandidate) => LocalCandidate) => {
    setCandidates((current) => current.map((candidate) => candidate.id === candidateId ? update(candidate) : candidate))
  }

  const runModelEvaluation = async (candidateId: string, candidateOverride?: LocalCandidate, allowAutomaticRepair = true) => {
    const candidate = candidateOverride ?? candidates.find((item) => item.id === candidateId)
    if (!candidate) return
    setEvaluatingCandidateId(candidateId)
    setNotice(null)
    try {
      const evaluation = await skillWorkbenchBridge.evaluateCandidate(candidate)
      const evaluated = recordModelEvaluation(candidate, evaluation)
      updateCandidate(candidateId, () => evaluated)
      if (evaluation.status === "passed" && evaluation.score >= 80) {
        setNotice(`自动质量检查通过：${evaluation.score} 分，等待最终发布确认。`)
        return
      }
      if (!allowAutomaticRepair) {
        setNotice("自动质量修正后仍未达到发布标准，请重新沉淀或查看运行日志。")
        void recordUiLog({ action: "candidate.auto_remediation", stage: "completed", status: "error", code: "CANDIDATE_AUTO_REEVALUATION_FAILED", message: "自动质量修正后仍未达到发布标准", location: "SkillWorkbench.tsx:runModelEvaluation", detail: `复评得分：${evaluation.score}` })
        return
      }
      setRemediatingCandidateId(candidateId)
      setNotice("自动质量检查发现题材残留，正在保持写作机制不变地修正并复评。")
      void recordUiLog({ action: "candidate.auto_remediation", stage: "started", status: "started", code: "CANDIDATE_AUTO_REMEDIATION_STARTED", message: "开始自动修正候选的题材残留", location: "SkillWorkbench.tsx:runModelEvaluation", detail: `初次评测得分：${evaluation.score}` })
      try {
        const remediation = await skillWorkbenchBridge.remediateCandidate(evaluated)
        const repaired = applyCandidateRemediation(evaluated, remediation)
        updateCandidate(candidateId, () => repaired)
        void recordUiLog({ action: "candidate.auto_remediation", stage: "applied", status: "success", code: "CANDIDATE_AUTO_REMEDIATION_APPLIED", message: "候选已自动修正为通用写作机制", location: "SkillWorkbench.tsx:runModelEvaluation", detail: "保留原有叙事机制，移除样本主题和领域残留。" })
        await runModelEvaluation(candidateId, repaired, false)
      } catch (repairError) {
        setNotice(`自动质量修正失败：${errorMessage(repairError)}`)
        void recordUiLog({ action: "candidate.auto_remediation", stage: "failed", status: "error", code: "CANDIDATE_AUTO_REMEDIATION_FAILED", message: "自动质量修正失败", location: "SkillWorkbench.tsx:runModelEvaluation", detail: errorMessage(repairError) })
      } finally {
        setRemediatingCandidateId(null)
      }
    } catch (error) {
      setNotice(`模型评测失败：${errorMessage(error)}`)
    } finally {
      setEvaluatingCandidateId(null)
      void refreshDiagnosticLogs()
    }
  }

  const exportCandidate = async (candidateId: string, candidateOverride?: LocalCandidate) => {
    const candidate = candidateOverride ?? candidates.find((item) => item.id === candidateId)
    if (!candidate) return
    setPublishingCandidateId(candidateId)
    setPublishProgress({ stage: "fetching", message: "正在安全同步目标 Skill 仓库" })
    try {
      const publishId = preparePublishCandidate(candidate)
      const result = await skillWorkbenchBridge.publishReleaseCandidate(publishId)
      setPublishJobs((current) => ({ ...current, [candidateId]: result }))
      updateCandidate(candidateId, (current) => markCandidateExported(current, result.version, result.manifestPath ?? ""))
      setNotice(result.remoteVerifiedAt ? `stable 已发布并完成远端验证：${result.commitUrl ?? result.commitSha}` : `stable 已提交到本地仓库：${result.manifestPath}`)
      setStableSnapshot(await skillWorkbenchBridge.loadStableRepositorySnapshot())
    } catch (error) {
      setNotice(`正式版本发布失败：${errorMessage(error)}`)
    } finally {
      setPublishingCandidateId(null)
      setPublishProgress(null)
      void refreshDiagnosticLogs()
    }
  }

  const confirmAndPublishCandidate = async (candidateId: string) => {
    const candidate = candidates.find((item) => item.id === candidateId)
    if (!candidate) return
    if (candidate.modelEvaluation?.status !== "passed" || candidate.modelEvaluation.score < 80) {
      setNotice("模型评测尚未通过，不能发布 stable Skill。")
      return
    }
    const review: HumanReview = {
      status: "approved",
      reviewer: "本机用户",
      notes: "已在工作台确认通用写作结构、模型评测与风险边界。",
      reviewedAt: new Date().toISOString(),
    }
    const approved = recordHumanReview(candidate, review)
    const nextCandidates = candidates.map((item) => item.id === candidateId ? approved : item)
    setCandidates(nextCandidates)
    await skillWorkbenchBridge.save({ session, candidates: nextCandidates })
    setNotice("最终发布确认已记录，正在生成并同步 stable Skill。")
    void recordUiLog({ action: "candidate.publish_confirmation", stage: "human_confirmation", status: "success", code: "CANDIDATE_PUBLISH_CONFIRMED", message: "用户已确认发布 stable Skill", location: "SkillWorkbench.tsx:confirmAndPublishCandidate", detail: "已记录最终确认；不记录 Skill 正文或来源稿件。" })
    void exportCandidate(candidateId, approved)
  }

  const resetDeposit = () => {
    setSession(emptySession())
    setNotice(null)
    void recordUiLog({ action: "workflow.deposit", stage: "reset", status: "info", code: "WORKFLOW_DEPOSIT_RESET", message: "开始新的 Skill 沉淀流程", location: "SkillWorkbench.tsx:resetDeposit", detail: null })
  }

  const clearDiagnosticLogs = async () => {
    if (!window.confirm("清空全部运行日志？此操作无法从工作台恢复。")) return
    try {
      await skillWorkbenchBridge.clearDiagnosticLogs()
      setDiagnosticLogs([])
    } catch (error) {
      setNotice(`清空运行日志失败：${errorMessage(error)}`)
    }
  }

  return (<>
    <WorkbenchShell page={page} candidateCount={candidates.length} onPageChange={(nextPage) => { setNotice(null); setPage(nextPage) }}>
      {page === "deposit" ? <DepositPage session={session} notice={notice} processing={mediaProcessing} progressMessage={mediaProgress} proofreading={proofreading} analyzing={analyzing} onRecognizeLink={recognizeLink} onImportMedia={importMedia} onUseTranscript={useTranscript} onUpdateTranscript={updateTranscript} onProofread={proofread} onFinalizeProofread={finalizeProofread} onReset={resetDeposit} /> : null}
      {page === "library" ? <LibraryPage candidates={candidates} stableSnapshot={stableSnapshot} publishJobs={publishJobs} notice={notice} onPublishConfirmed={(id) => void confirmAndPublishCandidate(id)} onRetryExport={exportCandidate} evaluatingCandidateId={evaluatingCandidateId} remediatingCandidateId={remediatingCandidateId} publishingCandidateId={publishingCandidateId} publishProgress={publishProgress} /> : null}
      {page === "diagnostics" ? <DiagnosticsPage candidates={candidates} health={health} stableSnapshot={stableSnapshot} refreshing={healthRefreshing} onRefresh={refreshHealth} logs={diagnosticLogs} logsRefreshing={logsRefreshing} onRefreshLogs={() => void refreshDiagnosticLogs()} onClearLogs={() => void clearDiagnosticLogs()} updater={updater} /> : null}
    </WorkbenchShell>
    {updater.status === "available" && !updatePromptDismissed ? <UpdatePrompt updater={updater} onDismiss={() => setUpdatePromptDismissed(true)} /> : null}
  </>)
}
