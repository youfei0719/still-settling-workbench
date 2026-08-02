import {
  type ReactElement,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react"
import {
  analyzeText,
  approveAndPublishWritingSkill,
  createHumanReviewTemplate,
  createWritingSkill,
  fetchCodexSkillPack,
  fetchExternalGates,
  fetchLocalSettings,
  fetchOverview,
  publishCodexSkillPackToGithub,
  updateSkillGovernance,
  updateTemplateReview,
  verifyLocalSettings,
  WorkbenchApiError,
} from "@/api/workbench"
import { fallbackOverview } from "@/data/fallback"
import {
  extractAndTranscribeWithLocalConnector,
  LocalConnectorExtractionError,
  LocalConnectorUnavailableError,
  type LocalTranscriptResponse,
} from "@/lib/localConnector"
import type {
  AnalyzeTextResponse,
  CodexSkillPackResponse,
  CodexSkillPublishResponse,
  ExternalGateReport,
  LinkTaskResponse,
  LocalSettingsStatus,
  SkillApprovalAndPublishResponse,
  SkillGovernancePayload,
  TemplatePattern,
  TemplateReviewPayload,
  VideoUploadResponse,
  WorkbenchOverview,
  WritingPresetCreatePayload,
} from "@/types/workbench"
import { AnalysisWorkspace } from "./components/workbench/AnalysisWorkspace"
import { AppShell, type PageKey } from "./components/workbench/AppShell"
import { CodexSyncPanel } from "./components/workbench/CodexSyncPanel"
import { InitialSetupPanel } from "./components/workbench/InitialSetupPanel"
import { LinkConsole } from "./components/workbench/LinkConsole"
import { ReviewExport } from "./components/workbench/ReviewExport"
import { TemplateLibrary } from "./components/workbench/TemplateLibrary"

function localConnectorVideoUpload(
  transcript: LocalTranscriptResponse,
): VideoUploadResponse {
  const sourceId = `local-${Date.now()}`
  const source = {
    id: sourceId,
    input_type: "transcript" as const,
    title: transcript.title,
    url: transcript.source_url,
    status: "completed" as const,
    material_path: "仅在本机临时处理，转写后已删除",
    created_at: new Date().toISOString(),
  }
  return {
    source_video: source,
    audio_path: "仅在本机临时处理，转写后已删除",
    frame_paths: [],
    extraction_status: "completed",
    asr_status: "completed",
    asr_provider: transcript.provider,
    asr_text: transcript.text,
    ocr_status: "skipped",
    ocr_provider: "未使用",
    ocr_text: "",
    transcript: {
      id: `local-transcript-${Date.now()}`,
      source_video_id: sourceId,
      asr_text: transcript.text,
      ocr_text: "",
      content_text: transcript.text,
      timestamps: transcript.timestamps,
      confidence: 0.75,
      source: "local_funasr",
    },
    correction_status: "completed",
    corrections: [],
    unresolved_fragments: [],
    transcript_quality_score: 75,
    transcript_quality_message:
      "文稿由本机 ASR 生成；可在工作台继续审阅与沉淀。",
    context_terms: [],
    message: transcript.message,
    asr_message: "本机 ASR 已完成。",
    ocr_message: "本次未运行 OCR。",
    next_step: "云端仅接收文稿，用于结构分析与历史保存。",
    fallback_inputs: [],
    media_cleanup_status: "completed",
    media_cleanup_message:
      "视频、音频和浏览器会话仅在本机临时处理，未上传服务器。",
  }
}

function localConnectorLinkTask(upload: VideoUploadResponse): LinkTaskResponse {
  return {
    source_video: upload.source_video,
    parser_status: "completed",
    parser_provider: "本机连接器（yt-dlp + FunASR）",
    output_dir: null,
    downloaded_files: [upload.source_video.title],
    video_upload: upload,
    parser_error_code: null,
    parser_error_title: null,
    parser_error_detail: null,
    parser_action_items: [],
    message: `本机连接器已完成下载与转写。${upload.message}`,
    fallback_inputs: [],
  }
}

export default function App() {
  const [page, setPage] = useState<PageKey>("link")
  const [overview, setOverview] = useState<WorkbenchOverview>(fallbackOverview)
  const [skillPack, setSkillPack] = useState<CodexSkillPackResponse | null>(
    null,
  )
  const [localSettings, setLocalSettings] =
    useState<LocalSettingsStatus | null>(null)
  const [url, setUrl] = useState("")
  const [title, setTitle] = useState("明星事件公开回应引发讨论")
  const [, setText] = useState("")
  const [analysis, setAnalysis] = useState<AnalyzeTextResponse | null>(null)
  const [savedSkill, setSavedSkill] = useState<TemplatePattern | null>(null)
  const [linkTask, setLinkTask] = useState<LinkTaskResponse | null>(null)
  const [videoUpload, setVideoUpload] = useState<VideoUploadResponse | null>(
    null,
  )
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(
    null,
  )
  const [evidenceTargetId, setEvidenceTargetId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [presetSaving, setPresetSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [skillPublishing, setSkillPublishing] = useState(false)
  const [skillPublishResult, setSkillPublishResult] =
    useState<CodexSkillPublishResponse | null>(null)
  const [skillPublishError, setSkillPublishError] = useState<string | null>(
    null,
  )
  const [toast, setToast] = useState<string | null>(null)
  const [externalGates, setExternalGates] = useState<ExternalGateReport | null>(
    null,
  )
  const [externalGateLoading, setExternalGateLoading] = useState(false)
  const [authenticationRequired, setAuthenticationRequired] = useState(false)

  const refreshSkillPack = useCallback(async () => {
    try {
      setSkillPack(await fetchCodexSkillPack())
    } catch {
      setSkillPack(null)
    }
  }, [])

  const refreshExternalGates = useCallback(
    async (options?: { runLink?: boolean; expectModel?: boolean }) => {
      setExternalGateLoading(true)
      try {
        setExternalGates(await fetchExternalGates(undefined, options))
      } catch (event) {
        setToast(event instanceof Error ? event.message : "刷新外部门禁失败")
      } finally {
        setExternalGateLoading(false)
      }
    },
    [],
  )

  const handleCreateHumanReviewTemplate = async () => {
    const result = await createHumanReviewTemplate()
    setToast(result.message)
  }

  useEffect(() => {
    fetchOverview()
      .then((data) => {
        setOverview(data)
      })
      .catch((reason) => {
        if (
          reason instanceof WorkbenchApiError &&
          (reason.status === 401 || reason.status === 403)
        ) {
          setAuthenticationRequired(true)
          return
        }
        setOverview(fallbackOverview)
      })
    void refreshSkillPack()
    void refreshExternalGates()
    void fetchLocalSettings()
      .then(setLocalSettings)
      .catch(() => setLocalSettings(null))
  }, [refreshExternalGates, refreshSkillPack])

  useEffect(() => {
    if (!toast) return
    const timeout = window.setTimeout(() => setToast(null), 2400)
    return () => window.clearTimeout(timeout)
  }, [toast])

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" })
  }, [])

  const mergedOverview = useMemo<WorkbenchOverview>(() => {
    return {
      ...overview,
      templates: overview.templates.filter(
        (template, index, list) =>
          list.findIndex((item) => item.id === template.id) === index,
      ),
      recent_analyses: analysis
        ? [analysis.analysis, ...overview.recent_analyses]
        : overview.recent_analyses,
    }
  }, [analysis, overview])
  const evidenceTarget =
    mergedOverview.templates.find(
      (template) => template.id === evidenceTargetId,
    ) || null

  const handleAnalyzeLink = async () => {
    setError(null)
    setAnalysis(null)
    setSavedSkill(null)
    setLinkTask(null)
    setVideoUpload(null)
    setLoading(true)
    try {
      const localTranscript = await extractAndTranscribeWithLocalConnector(url)
      const upload = localConnectorVideoUpload(localTranscript)
      setLinkTask(localConnectorLinkTask(upload))
      setVideoUpload(upload)
      const extractedTitle = upload.source_video.title || title
      const extractedText = localTranscript.text

      setTitle(extractedTitle)
      setText(extractedText)
      const analysisResponse = await analyzeText({
        title: extractedTitle,
        content: extractedText,
        input_type: "transcript",
        url: localTranscript.source_url,
        asr_text: extractedText,
        transcript_source: "local_funasr",
        transcript_confidence: 0.75,
      })
      const persistedUpload: VideoUploadResponse = {
        ...upload,
        source_video: analysisResponse.source_video,
        transcript: analysisResponse.transcript,
      }
      setLinkTask(localConnectorLinkTask(persistedUpload))
      setVideoUpload(persistedUpload)
      setAnalysis(analysisResponse)
      setSavedSkill(null)
      setToast("已完成拆解，可在当前页确认结果")
    } catch (event) {
      if (
        event instanceof LocalConnectorUnavailableError ||
        event instanceof LocalConnectorExtractionError
      ) {
        setError(event.message)
      } else {
        setError(
          event instanceof Error ? event.message : "本机提取视频稿件失败",
        )
      }
      setToast("本机媒体处理未完成，云端没有接收视频")
    } finally {
      setLoading(false)
    }
  }

  const handleConfirmTranscript = async (confirmedText: string) => {
    const cleanedText = confirmedText.trim()
    if (cleanedText.length < 10 || !videoUpload?.transcript) {
      setError("请先确认并补全视频稿件，再继续拆解。")
      return
    }
    setError(null)
    setLoading(true)
    try {
      const confirmedTranscript = {
        ...videoUpload.transcript,
        content_text: cleanedText,
        confidence: 1,
        source: `${videoUpload.transcript.source}+human_review`,
      }
      const confirmedUpload: VideoUploadResponse = {
        ...videoUpload,
        transcript: confirmedTranscript,
        correction_status: "completed",
        unresolved_fragments: [],
        transcript_quality_score: 100,
        transcript_quality_message: "稿件已由你人工确认，可以继续拆解。",
      }
      const confirmedLinkTask = linkTask
        ? {
            ...linkTask,
            parser_status: "completed" as const,
            parser_error_code: null,
            parser_error_title: null,
            parser_error_detail: null,
            video_upload: confirmedUpload,
            message: "视频稿件已人工确认，可以继续拆解写作结构。",
          }
        : null

      setText(cleanedText)
      setVideoUpload(confirmedUpload)
      setLinkTask(confirmedLinkTask)
      const analysisResponse = await analyzeText({
        title: confirmedUpload.source_video.title || title,
        content: cleanedText,
        input_type: "transcript",
        url: confirmedUpload.source_video.url || url,
        source_video_id: confirmedUpload.source_video.id,
        author: confirmedUpload.source_video.author,
        publish_time: confirmedUpload.source_video.publish_time,
        source_created_at: confirmedUpload.source_video.created_at,
        asr_text: confirmedUpload.asr_text,
        ocr_text: confirmedUpload.ocr_text,
        transcript_source: confirmedTranscript.source,
        transcript_confidence: confirmedTranscript.confidence,
      })
      setAnalysis(analysisResponse)
      setToast("稿件已确认，写法拆解已完成")
    } catch (event) {
      setError(event instanceof Error ? event.message : "确认稿件后拆解失败")
    } finally {
      setLoading(false)
    }
  }

  const handleReviewTemplate = async (
    templateId: string,
    payload: TemplateReviewPayload,
  ): Promise<TemplatePattern> => {
    const updated = await updateTemplateReview(templateId, payload)
    setOverview((current) => {
      const exists = current.templates.some(
        (template) => template.id === updated.id,
      )
      const templates = exists
        ? current.templates.map((template) =>
            template.id === updated.id ? updated : template,
          )
        : [updated, ...current.templates]
      return {
        ...current,
        templates,
      }
    })
    await refreshSkillPack()
    setToast(
      updated.disabled_reason
        ? "Skill 已停用；需要同步给团队时，请到系统诊断发布"
        : "Skill 复盘已保存；需要同步给团队时，请到系统诊断发布",
    )
    return updated
  }

  const handleGovernSkill = async (
    templateId: string,
    payload: SkillGovernancePayload,
  ): Promise<TemplatePattern> => {
    const updated = await updateSkillGovernance(templateId, payload)
    setOverview((current) => ({
      ...current,
      templates: current.templates.map((template) =>
        template.id === updated.id ? updated : template,
      ),
    }))
    await refreshSkillPack()
    setToast(
      `Skill 已更新为${updated.status === "active" ? "正式" : updated.status === "paused" ? "暂停" : updated.status === "retired" ? "退役" : "候选"}状态`,
    )
    return updated
  }

  const handleApproveAndPublishSkill = async (
    templateId: string,
    payload: SkillGovernancePayload,
  ): Promise<SkillApprovalAndPublishResponse> => {
    setSkillPublishing(true)
    setSkillPublishError(null)
    try {
      const result = await approveAndPublishWritingSkill(templateId, payload)
      setOverview((current) => ({
        ...current,
        templates: current.templates.map((template) =>
          template.id === result.skill.id ? result.skill : template,
        ),
      }))
      setSkillPublishResult(result.publish)
      await refreshSkillPack()
      setToast(`已审核为正式并同步 GitHub：${result.publish.repository}`)
      return result
    } catch (event) {
      const message =
        event instanceof Error ? event.message : "Skill 审核与 GitHub 同步失败"
      setSkillPublishError(message)
      throw new Error(message)
    } finally {
      setSkillPublishing(false)
    }
  }

  const handleSaveWritingPreset = async (
    payload: WritingPresetCreatePayload,
  ) => {
    if (!analysis) return
    setPresetSaving(true)
    try {
      const created = await createWritingSkill(payload)
      setOverview((current) => ({
        ...current,
        templates: [
          created,
          ...current.templates.filter((template) => template.id !== created.id),
        ],
      }))
      setSelectedTemplateId(created.id)
      setSavedSkill(created)
      setEvidenceTargetId(null)
      setToast(
        (created.source_count || 0) > 1
          ? `已合并到「${created.name}」，当前有 ${created.source_count} 个结构来源`
          : "已加入站内 Skill 库；补齐 3 个来源、发布评测和主审后才能发布给团队",
      )
      await refreshSkillPack()
    } catch (event) {
      setToast(event instanceof Error ? event.message : "写作 Skill 保存失败")
    } finally {
      setPresetSaving(false)
    }
  }

  const handlePublishSkillPack = async () => {
    setSkillPublishing(true)
    setSkillPublishError(null)
    try {
      const verification = await verifyLocalSettings()
      if (!verification.publish_ready) {
        throw new Error(verification.action_items[0] || verification.message)
      }
      const publish = await publishCodexSkillPackToGithub()
      setSkillPublishResult(publish)
      await refreshSkillPack()
      setToast(
        publish.status === "published"
          ? `已发布到 GitHub：${publish.repository}`
          : `GitHub 已是最新版：${publish.repository}`,
      )
    } catch (event) {
      const message =
        event instanceof Error ? event.message : "请检查 gh 登录和网络"
      setSkillPublishError(message)
      setToast(`GitHub 发布失败：${message}`)
    } finally {
      setSkillPublishing(false)
    }
  }

  const handleContinueEvidence = (template: TemplatePattern) => {
    setEvidenceTargetId(template.id)
    setSelectedTemplateId(template.id)
    setUrl("")
    setText("")
    setAnalysis(null)
    setSavedSkill(null)
    setLinkTask(null)
    setVideoUpload(null)
    setError(null)
    setPage("link")
    setToast(
      `正在为「${template.name}」补充第 ${(template.source_count || 0) + 1}/3 个来源`,
    )
  }

  const content = {
    link: (
      <LinkConsole
        url={url}
        loading={loading}
        error={error}
        linkTask={linkTask}
        videoUpload={videoUpload}
        analysis={analysis}
        onUrlChange={setUrl}
        onAnalyzeLink={handleAnalyzeLink}
        onConfirmTranscript={handleConfirmTranscript}
        onViewAnalysis={() => setPage("analysis")}
        evidenceTarget={evidenceTarget}
      />
    ),
    analysis: (
      <AnalysisWorkspace
        analysis={analysis}
        recentAnalyses={mergedOverview.recent_analyses}
        onSavePreset={handleSaveWritingPreset}
        savingPreset={presetSaving}
        savedSkill={savedSkill}
        onStartAnother={() => {
          setUrl("")
          setText("")
          setAnalysis(null)
          setSavedSkill(null)
          setLinkTask(null)
          setVideoUpload(null)
          setError(null)
          setEvidenceTargetId(null)
          setPage("link")
        }}
        onOpenSkillLibrary={() => setPage("templates")}
        onPublishSkillPack={() => void handlePublishSkillPack()}
        templates={mergedOverview.templates}
        skillPack={skillPack}
        skillPublishing={skillPublishing}
        skillPublishError={skillPublishError}
        skillPublishResult={skillPublishResult}
        preselectedMergeTargetId={evidenceTargetId}
      />
    ),
    templates: (
      <TemplateLibrary
        templates={mergedOverview.templates}
        selectedTemplateId={selectedTemplateId}
        onReviewTemplate={handleReviewTemplate}
        onGovernSkill={handleGovernSkill}
        onApproveAndPublish={handleApproveAndPublishSkill}
        onContinueEvidence={handleContinueEvidence}
      />
    ),
    diagnostics: (
      <div className="page-grid diagnostics-layout">
        <InitialSetupPanel onSettingsChanged={setLocalSettings} />
        <CodexSyncPanel
          skillPack={skillPack}
          publishResult={skillPublishResult}
          publishError={skillPublishError}
          publishing={skillPublishing}
          onPublish={() => void handlePublishSkillPack()}
          localSettings={localSettings}
        />
        <ReviewExport
          analysis={analysis}
          hotspotResult={null}
          selectedScript={null}
          generatedScripts={mergedOverview.generated_scripts}
          onSelectScript={() => undefined}
          onUpdateScript={async () => {
            throw new Error("请在审核导出页面更新脚本。")
          }}
          onToast={setToast}
          externalGates={externalGates}
          externalGateLoading={externalGateLoading}
          onRefreshExternalGates={refreshExternalGates}
          onCreateHumanReviewTemplate={handleCreateHumanReviewTemplate}
          onlyDiagnostics
        />
      </div>
    ),
  } satisfies Record<PageKey, ReactElement>

  if (authenticationRequired) {
    return (
      <main className="signin-page">
        <section className="signin-panel">
          <p className="section-eyebrow">访问受限</p>
          <h1>请从 CPM 健康中台进入</h1>
        </section>
      </main>
    )
  }

  return (
    <>
      <AppShell activePage={page} onNavigate={setPage}>
        {content[page]}
      </AppShell>
      {toast ? (
        <div className="toast" role="status">
          {toast}
        </div>
      ) : null}
    </>
  )
}
