import { type ReactElement, useCallback, useEffect, useMemo, useState } from "react"
import {
  analyzeText,
  approveAndPublishWritingSkill,
  cancelVideoExtractionTask,
  createHumanReviewTemplate,
  createWritingSkill,
  fetchCodexSkillPack,
  fetchExternalGates,
  fetchLocalSettings,
  fetchModelStatus,
  fetchOverview,
  fetchServerMediaTask,
  fetchVideoExtractionTask,
  fetchVideoExtractionTasks,
  updateGeneratedScript,
  publishCodexSkillPackToGithub,
  retryVideoExtractionTask,
  startServerMediaTask,
  startVideoExtractionTask,
  updateSkillGovernance,
  updateTemplateReview,
  verifyLocalSettings,
  warmupModels,
  WorkbenchApiError,
} from "@/api/workbench"
import { fallbackOverview } from "@/data/fallback"
import { createWritingProject } from "@/lib/writingProject"
import type {
  AnalyzeTextResponse,
  CodexSkillPackResponse,
  CodexSkillPublishResponse,
  ExternalGateReport,
  GeneratedScript,
  LinkTaskResponse,
  LocalSettingsStatus,
  ModelRuntimeStatus,
  SkillGovernancePayload,
  SkillApprovalAndPublishResponse,
  ServerMediaTask,
  TemplatePattern,
  TemplateReviewPayload,
  VideoExtractionTask,
  VideoUploadResponse,
  WorkbenchOverview,
  WritingPresetCreatePayload,
  WritingProjectState,
} from "@/types/workbench"
import { AnalysisWorkspace } from "./components/workbench/AnalysisWorkspace"
import { AppShell, type PageKey } from "./components/workbench/AppShell"
import { ContentWorkflow } from "./components/workbench/ContentWorkflow"
import { ProjectsPanel } from "./components/workbench/ProjectsPanel"
import { ReferenceLibraryPanel } from "./components/workbench/ReferenceLibraryPanel"
import { SkillFactoryHome } from "./components/workbench/SkillFactoryHome"
import { CodexSyncPanel } from "./components/workbench/CodexSyncPanel"
import { InitialSetupPanel } from "./components/workbench/InitialSetupPanel"
import { LinkConsole } from "./components/workbench/LinkConsole"
import { MaterialTaskPanel } from "./components/workbench/MaterialTaskPanel"
import { ReviewExport } from "./components/workbench/ReviewExport"
import { TemplateLibrary } from "./components/workbench/TemplateLibrary"

const ACTIVE_EXTRACTION_TASK_KEY = "douyin-workbench-active-extraction-task-id"

function linkTaskFromServerMediaTask(task: ServerMediaTask): LinkTaskResponse {
  const transcriptText = task.result?.transcript.trim() || ""
  const sourceVideo = {
    id: task.id,
    input_type: "douyin_url" as const,
    title: task.result?.title || "抖音视频",
    url: task.source_url,
    author: task.result?.author || null,
    publish_time: task.result?.publish_time || null,
    status: transcriptText ? ("completed" as const) : ("failed" as const),
    material_path: null,
    created_at: task.created_at,
  }
  const upload: VideoUploadResponse | null = transcriptText
    ? {
        source_video: sourceVideo,
        extraction_status: "completed",
        frame_paths: [],
        asr_status: "completed",
        asr_provider: task.result?.provider || "外部转写 API",
        asr_text: transcriptText,
        ocr_status: "skipped",
        ocr_provider: "未启用",
        ocr_text: "",
        transcript: {
          id: `transcript_${task.id}`,
          source_video_id: sourceVideo.id,
          asr_text: transcriptText,
          ocr_text: "",
          content_text: transcriptText,
          timestamps: task.result?.timestamps || [],
          confidence: 0.75,
          source: "external_asr",
        },
        correction_status: "completed",
        corrections: [],
        unresolved_fragments: [],
        transcript_quality_score: 75,
        transcript_quality_message: "已获得外部转写文稿，可进入结构分析。",
        context_terms: [],
        message: "服务器已完成临时媒体处理，视频和音频已清理。",
        asr_message: "外部转写 API 已返回文稿。",
        ocr_message: "本次链接任务未执行 OCR。",
        next_step: "可继续拆解写作结构。",
        fallback_inputs: ["上传字幕文件", "粘贴转写文本"],
        media_cleanup_status: "completed",
        media_cleanup_message: "视频和音频仅存在于任务临时目录，已清理。",
      }
    : null
  return {
    source_video: sourceVideo,
    parser_status: transcriptText ? "completed" : "failed",
    parser_provider: "主站媒体任务（yt-dlp + 外部转写 API）",
    output_dir: null,
    downloaded_files: [],
    video_upload: upload,
    parser_error_code: transcriptText ? null : "no_media",
    parser_error_title: transcriptText ? null : "未识别出视频稿件",
    parser_error_detail: transcriptText ? null : task.error || "服务器没有返回可分析文稿。",
    parser_action_items: transcriptText ? [] : ["上传字幕文件", "粘贴转写文本"],
    message: transcriptText
      ? "主站已完成下载、转写并清理临时媒体。"
      : task.error || "主站媒体任务未完成。",
    fallback_inputs: transcriptText ? [] : ["上传字幕文件", "粘贴转写文本"],
  }
}

export default function App() {
  const [page, setPage] = useState<PageKey>("create")
  const [overview, setOverview] = useState<WorkbenchOverview>(fallbackOverview)
  const [skillPack, setSkillPack] = useState<CodexSkillPackResponse | null>(
    null,
  )
  const [modelStatus, setModelStatus] = useState<ModelRuntimeStatus | null>(
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
  const [serverMediaTask, setServerMediaTask] =
    useState<ServerMediaTask | null>(null)
  const [videoExtractionTask, setVideoExtractionTask] =
    useState<VideoExtractionTask | null>(null)
  const [videoExtractionTasks, setVideoExtractionTasks] = useState<
    VideoExtractionTask[]
  >([])
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(
    null,
  )
  const [evidenceTargetId, setEvidenceTargetId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [presetSaving, setPresetSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploadNotice, setUploadNotice] = useState<string | null>(null)
  const [runAsr, setRunAsr] = useState(true)
  const [runOcr, setRunOcr] = useState(true)
  const [extractionLoading, setExtractionLoading] = useState(false)
  const [warmupLoading, setWarmupLoading] = useState(false)
  const [skillPublishing, setSkillPublishing] = useState(false)
  const [skillPublishResult, setSkillPublishResult] =
    useState<CodexSkillPublishResponse | null>(null)
  const [skillPublishError, setSkillPublishError] = useState<string | null>(
    null,
  )
  const [toast, setToast] = useState<string | null>(null)
  const [externalGates, setExternalGates] =
    useState<ExternalGateReport | null>(null)
  const [externalGateLoading, setExternalGateLoading] = useState(false)
  const [authenticationRequired, setAuthenticationRequired] = useState(false)
  const [draftResult, setDraftResult] = useState<import("@/types/workbench").DraftRewriteResponse | null>(null)
  const [selectedDraftScript, setSelectedDraftScript] = useState<GeneratedScript | null>(null)

  // Phase 1：WritingProject 仅保存在前端内存（App 持有），刷新即清空。
  const [writingProjects, setWritingProjects] = useState<WritingProjectState[]>([])
  const [activeWritingProjectId, setActiveWritingProjectId] = useState<
    string | null
  >(null)

  const refreshVideoExtractionTasks = useCallback(async () => {
    try {
      setVideoExtractionTasks(await fetchVideoExtractionTasks(8))
    } catch {
      setVideoExtractionTasks([])
    }
  }, [])

  const refreshSkillPack = useCallback(async () => {
    try {
      setSkillPack(await fetchCodexSkillPack())
    } catch {
      setSkillPack(null)
    }
  }, [])

  const refreshExternalGates = useCallback(
    async (options?: {
      runLink?: boolean
      expectModel?: boolean
    }) => {
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
    fetchModelStatus()
      .then(setModelStatus)
      .catch(() => setModelStatus(null))
    void refreshSkillPack()
    void refreshVideoExtractionTasks()
    void refreshExternalGates()
    void fetchLocalSettings().then(setLocalSettings).catch(() => setLocalSettings(null))
  }, [refreshExternalGates, refreshVideoExtractionTasks, refreshSkillPack])

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
    mergedOverview.templates.find((template) => template.id === evidenceTargetId) ||
    null

  const handleAnalyzeLink = async () => {
    setError(null)
    setAnalysis(null)
    setSavedSkill(null)
    setLinkTask(null)
    setVideoUpload(null)
    setServerMediaTask(null)
    setLoading(true)
    try {
      let task = await startServerMediaTask(url)
      setServerMediaTask(task)
      while (task.status === "queued" || task.status === "processing") {
        await new Promise((resolve) => window.setTimeout(resolve, 1500))
        task = await fetchServerMediaTask(task.id)
        setServerMediaTask(task)
      }
      const response = linkTaskFromServerMediaTask(task)
      setLinkTask(response)
      setVideoUpload(response.video_upload || null)
      const extractedTitle =
        response.video_upload?.source_video.title ||
        response.source_video.title ||
        title
      const extractedText =
        response.video_upload?.transcript?.content_text ||
        [response.video_upload?.asr_text, response.video_upload?.ocr_text]
          .filter(Boolean)
          .join("\n")
      if (
        response.parser_status !== "completed" ||
        extractedText.trim().length < 10
      ) {
        setText("")
        setUploadNotice(null)
        setError(response.parser_error_detail || "主站没有取得可分析的视频稿件。")
        setToast("主站媒体任务未完成")
        return
      }

      setTitle(extractedTitle)
      setText(extractedText)
      setUploadNotice("已从抖音链接真实提取视频稿件，正在拆解写作结构。")
      const analysisResponse = await analyzeText({
        title: extractedTitle,
        content: extractedText,
        input_type: "transcript",
        url: response.source_video.url || url,
        source_video_id: response.video_upload?.source_video.id,
        author: response.source_video.author,
        publish_time: response.source_video.publish_time,
        source_created_at: response.video_upload?.source_video.created_at,
        asr_text: response.video_upload?.asr_text,
        ocr_text: response.video_upload?.ocr_text,
        transcript_source: response.video_upload?.transcript?.source,
        transcript_confidence: response.video_upload?.transcript?.confidence,
      })
      setAnalysis(analysisResponse)
      setSavedSkill(null)
      setToast("已完成拆解，可在当前页确认结果")
    } catch (event) {
      setError(event instanceof Error ? event.message : "真实提取视频稿件失败")
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

  const applyVideoUploadResult = (response: VideoUploadResponse) => {
    setVideoUpload(response)
    const mergedText =
      response.transcript?.content_text ||
      [response.asr_text, response.ocr_text].filter(Boolean).join("\n")
    if (mergedText.trim().length >= 10) {
      setText(mergedText)
    }
    setUploadNotice(
      response.transcript
        ? "视频文字已提取，可以继续拆解写法。"
        : "视频已收到。若暂时没有自动文字，请上传字幕、转写文本或直接粘贴口播文案继续。",
    )
  }

  const rememberExtractionTask = (task: VideoExtractionTask) => {
    window.localStorage.setItem(ACTIVE_EXTRACTION_TASK_KEY, task.id)
  }

  const applyVideoExtractionTask = (task: VideoExtractionTask) => {
    setVideoExtractionTask(task)
    setVideoExtractionTasks((current) =>
      [task, ...current.filter((item) => item.id !== task.id)].slice(0, 8),
    )
    if (task.video_upload) {
      setTitle(task.video_upload.source_video.title)
      applyVideoUploadResult(task.video_upload)
    }
    if (task.status === "cancelled") {
      setUploadNotice(
        "自动文字提取已取消，可以上传字幕、转写文本或直接粘贴口播文案继续。",
      )
    }
  }

  const pollVideoExtractionTask = async (initialTask: VideoExtractionTask) => {
    rememberExtractionTask(initialTask)
    setExtractionLoading(
      initialTask.status === "queued" || initialTask.status === "processing",
    )
    let current = initialTask
    for (
      let index = 0;
      index < 180 &&
      (current.status === "queued" || current.status === "processing");
      index += 1
    ) {
      await new Promise((resolve) => window.setTimeout(resolve, 1200))
      current = await fetchVideoExtractionTask(current.id)
      applyVideoExtractionTask(current)
      if (current.cancel_requested) {
        setToast("取消请求已提交")
      }
    }
    if (current.video_upload) {
      applyVideoUploadResult(current.video_upload)
    }
    if (current.status === "completed") {
      setToast(
        current.transcript
          ? "视频文字已生成"
          : "暂时没有生成文字，请换一种输入继续",
      )
    } else if (current.status === "failed") {
      setError(current.error || "后台提取失败")
      setToast("后台提取失败")
    } else if (current.status === "cancelled") {
      setToast("后台提取已取消")
    }
    void refreshVideoExtractionTasks()
    setExtractionLoading(false)
    return current
  }

  useEffect(() => {
    const taskId = window.localStorage.getItem(ACTIVE_EXTRACTION_TASK_KEY)
    if (!taskId) return
    fetchVideoExtractionTask(taskId)
      .then((task) => {
        applyVideoExtractionTask(task)
        if (task.status === "queued" || task.status === "processing") {
          void pollVideoExtractionTask(task)
        }
      })
      .catch(() => {
        window.localStorage.removeItem(ACTIVE_EXTRACTION_TASK_KEY)
      })
  }, [pollVideoExtractionTask, applyVideoExtractionTask])

  const handleStartVideoExtraction = async (targetUpload = videoUpload) => {
    if (!targetUpload) {
      setError("请先上传视频，再启动自动文字提取。")
      return
    }
    setError(null)
    setExtractionLoading(true)
    try {
      const started = await startVideoExtractionTask(
        targetUpload.source_video.id,
        {
          run_asr: runAsr,
          run_ocr: runOcr,
        },
      )
      applyVideoExtractionTask(started)
      setToast("自动文字提取已启动")
      await pollVideoExtractionTask(started)
    } catch (event) {
      setError(event instanceof Error ? event.message : "后台提取启动失败")
      setToast("后台提取启动失败")
    } finally {
      setExtractionLoading(false)
    }
  }

  const handleCancelVideoExtraction = async () => {
    if (!videoExtractionTask) return
    setError(null)
    try {
      const cancelled = await cancelVideoExtractionTask(videoExtractionTask.id)
      applyVideoExtractionTask(cancelled)
      void refreshVideoExtractionTasks()
      setExtractionLoading(
        cancelled.status === "queued" || cancelled.status === "processing",
      )
      setToast(
        cancelled.status === "cancelled" ? "后台提取已取消" : "取消请求已提交",
      )
    } catch (event) {
      setError(event instanceof Error ? event.message : "取消后台提取失败")
      setToast("取消后台提取失败")
    }
  }

  const handleRetryVideoExtraction = async () => {
    if (!videoExtractionTask) return
    setError(null)
    setExtractionLoading(true)
    try {
      const retried = await retryVideoExtractionTask(videoExtractionTask.id)
      applyVideoExtractionTask(retried)
      setToast("自动文字提取已重试")
      await pollVideoExtractionTask(retried)
    } catch (event) {
      setError(event instanceof Error ? event.message : "重试后台提取失败")
      setToast("重试后台提取失败")
      setExtractionLoading(false)
    }
  }

  const handleWarmupCheck = async (execute = false) => {
    setError(null)
    setWarmupLoading(true)
    try {
      const response = await warmupModels({
        run_asr: runAsr,
        run_ocr: runOcr,
        execute,
      })
      setModelStatus({
        items: response.items,
        ready_count: response.items.filter((item) => item.available).length,
        total_count: response.items.length,
        message: response.message,
      })
      setToast(execute ? "模型预热请求已完成" : "模型预热检查完成")
    } catch (event) {
      setError(event instanceof Error ? event.message : "模型预热检查失败")
      setToast("模型预热检查失败")
    } finally {
      setWarmupLoading(false)
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

  const activeWritingProject =
    writingProjects.find((item) => item.id === activeWritingProjectId) || null

  const startWritingProject = (topic: string, supplement: string) => {
    const project = createWritingProject(topic, supplement)
    setWritingProjects((current) => [project, ...current])
    setActiveWritingProjectId(project.id)
    setPage("create")
    return project
  }

  const updateWritingProject = (
    projectId: string,
    patch: Partial<WritingProjectState>,
  ) => {
    setWritingProjects((current) =>
      current.map((item) =>
        item.id === projectId
          ? { ...item, ...patch, updatedAt: new Date().toISOString() }
          : item,
      ),
    )
  }

  const openWritingProject = (projectId: string) => {
    setActiveWritingProjectId(projectId)
    setPage("create")
  }

  const startNewWritingProject = () => {
    setActiveWritingProjectId(null)
    setPage("create")
  }

  const templateLibraryPage = (
    <TemplateLibrary
      templates={mergedOverview.templates}
      selectedTemplateId={selectedTemplateId}
      onReviewTemplate={handleReviewTemplate}
      onGovernSkill={handleGovernSkill}
      onApproveAndPublish={handleApproveAndPublishSkill}
      onContinueEvidence={handleContinueEvidence}
    />
  )

  const content = {
    create: (
      <ContentWorkflow
        project={activeWritingProject}
        templates={mergedOverview.templates}
        onStartProject={startWritingProject}
        onProjectChange={updateWritingProject}
        onNewProject={startNewWritingProject}
        onOpenStructures={() => setPage("structures")}
        onToast={setToast}
      />
    ),
    projects: (
      <ProjectsPanel
        projects={writingProjects}
        onOpenProject={openWritingProject}
        onNewProject={startNewWritingProject}
      />
    ),
    structures: templateLibraryPage,
    references: <ReferenceLibraryPanel />,
    factory: <SkillFactoryHome onNavigate={setPage} />,
    link: (
      <LinkConsole
        url={url}
        loading={loading}
        error={error}
        serverMediaTask={serverMediaTask}
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
    templates: templateLibraryPage,
    review: (
      <ReviewExport
        analysis={analysis}
        hotspotResult={draftResult}
        selectedScript={selectedDraftScript}
        generatedScripts={draftResult?.scripts || mergedOverview.generated_scripts}
        onSelectScript={(script) => setSelectedDraftScript(script)}
        onUpdateScript={async (scriptId, payload) => {
          const updated = await updateGeneratedScript(scriptId, payload)
          setDraftResult((current) => current ? { ...current, scripts: current.scripts.map((script) => script.id === updated.id ? updated : script) } : current)
          setSelectedDraftScript(updated)
          return updated
        }}
        onToast={setToast}
        externalGates={externalGates}
        externalGateLoading={externalGateLoading}
        onRefreshExternalGates={refreshExternalGates}
        onCreateHumanReviewTemplate={handleCreateHumanReviewTemplate}
      />
    ),
    settings: (
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
        <MaterialTaskPanel
          title={title}
          linkTask={linkTask}
          videoUpload={videoUpload}
          videoExtractionTask={videoExtractionTask}
          videoExtractionTasks={videoExtractionTasks}
          runAsr={runAsr}
          runOcr={runOcr}
          modelStatus={modelStatus}
          extractionLoading={extractionLoading}
          warmupLoading={warmupLoading}
          uploadNotice={uploadNotice}
          onRunAsrChange={setRunAsr}
          onRunOcrChange={setRunOcr}
          onWarmupCheck={() => void handleWarmupCheck(false)}
          onWarmupExecute={() => void handleWarmupCheck(true)}
          onStartVideoExtraction={() => void handleStartVideoExtraction()}
          onCancelVideoExtraction={() => void handleCancelVideoExtraction()}
          onRetryVideoExtraction={() => void handleRetryVideoExtraction()}
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
