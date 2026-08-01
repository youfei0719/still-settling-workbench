import type {
  AnalyzeTextResponse,
  CodexSkillPackResponse,
  CodexSkillPublishResponse,
  DraftDiagnosis,
  DraftInputPayload,
  DraftRewritePayload,
  DraftRewriteResponse,
  DraftRewriteTask,
  ExternalGateReport,
  GeneratedScript,
  GeneratedScriptUpdatePayload,
  GenerateHotspotResponse,
  HumanReviewItem,
  HumanReviewTemplateResponse,
  ModelCatalogResponse,
  ModelConnectionCheckResponse,
  LinkDiagnosticRecord,
  LinkTaskResponse,
  LlmRuntimeConfig,
  LocalSettingsStatus,
  LocalSettingsUpdatePayload,
  LocalSettingsVerification,
  SkillRepositorySetupResponse,
  ModelRuntimeStatus,
  ModelWarmupResponse,
  SelectionRewritePayload,
  SelectionRewriteResponse,
  SelectionRewriteSuggestionPayload,
  SelectionRewriteSuggestionResponse,
  SkillApprovalAndPublishResponse,
  SkillGovernancePayload,
  SkillPromotionReadiness,
  SkillReleaseEvaluationResponse,
  SkillMatch,
  TemplatePattern,
  TemplateReviewPayload,
  UploadTextPayload,
  VideoExtractionTask,
  VideoUploadResponse,
  WorkbenchCapabilities,
  WorkbenchOverview,
  WritingPresetCreatePayload,
} from "@/types/workbench"

const API_BASE = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"

export class WorkbenchApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = "WorkbenchApiError"
  }
}

function authorizationHeader(): Record<string, string> {
  const token = window.localStorage.getItem("access_token")
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function readApiErrorMessage(response: Response, fallback: string) {
  const raw = await response.text()
  if (!raw) return fallback

  try {
    const parsed = JSON.parse(raw) as { detail?: unknown; message?: unknown }
    if (typeof parsed.detail === "string") return parsed.detail
    if (typeof parsed.message === "string") return parsed.message
    if (Array.isArray(parsed.detail)) {
      const firstMessage = parsed.detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            return String((item as { msg: unknown }).msg)
          }
          return ""
        })
        .find(Boolean)
      if (firstMessage) return `请求参数需要调整：${firstMessage}`
    }
  } catch {
    // Plain text responses are handled below.
  }

  return raw.length > 180 ? fallback : raw
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers)
  headers.set("Content-Type", "application/json")
  for (const [name, value] of Object.entries(authorizationHeader())) {
    headers.set(name, value)
  }
  const response = await fetch(`${API_BASE}/api/v1/script-workbench${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    if (response.status === 404 && path.includes("/approve-and-publish")) {
      throw new Error(
        "本地发布服务尚未更新。请执行 scripts/workbench-local.sh stop 后再执行 start，然后重试。",
      )
    }
    const message = await readApiErrorMessage(
      response,
      `请求失败：${response.status}`,
    )
    throw new WorkbenchApiError(message, response.status)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export function fetchOverview() {
  return request<WorkbenchOverview>("/overview")
}

export async function authenticateWorkbench(email: string, password: string) {
  const response = await fetch(`${API_BASE}/api/v1/login/access-token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: email, password }),
  })
  if (!response.ok) {
    const message = await readApiErrorMessage(response, "登录失败")
    throw new WorkbenchApiError(message, response.status)
  }
  const payload = (await response.json()) as { access_token?: string }
  if (!payload.access_token) throw new Error("登录响应缺少访问令牌。")
  window.localStorage.setItem("access_token", payload.access_token)
}

export function fetchCodexSkillPack() {
  return request<CodexSkillPackResponse>("/codex-skill-pack")
}

export function publishCodexSkillPackToGithub() {
  return request<CodexSkillPublishResponse>(
    "/codex-skill-pack/publish-github",
    {
      method: "POST",
    },
  )
}

export function fetchLlmStatus() {
  return request<LlmRuntimeConfig>("/llm-status")
}

export function fetchCapabilities() {
  return request<WorkbenchCapabilities>("/capabilities")
}

export function fetchExternalGates(
  link?: string,
  options?: { runLink?: boolean; expectModel?: boolean },
) {
  const params = new URLSearchParams()
  if (link) params.set("link", link)
  if (options?.runLink) params.set("run_link", "true")
  if (options?.expectModel) params.set("expect_model", "true")
  const query = params.toString() ? `?${params.toString()}` : ""
  return request<ExternalGateReport>(`/external-gates${query}`)
}

export function fetchLocalSettings() {
  return request<LocalSettingsStatus>("/local-settings")
}

export function updateLocalSettings(payload: LocalSettingsUpdatePayload) {
  return request<LocalSettingsStatus>("/local-settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export function verifyLocalSettings() {
  return request<LocalSettingsVerification>("/local-settings/verify", {
    method: "POST",
  })
}

export function discoverConfiguredModels() {
  return request<ModelCatalogResponse>("/local-settings/models", { method: "POST" })
}

export function testConfiguredModel() {
  return request<ModelConnectionCheckResponse>("/local-settings/test-model", { method: "POST" })
}

export function connectGithubRepository(payload: {
  repository_url: string
  local_parent_path?: string
}) {
  return request<SkillRepositorySetupResponse>("/local-settings/connect-github", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function createGithubRepository(payload: {
  repository_name: string
  visibility: "private" | "public"
  local_parent_path?: string
}) {
  return request<SkillRepositorySetupResponse>("/local-settings/create-github", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function createLocalRepository(payload: {
  repository_name: string
  local_parent_path?: string
}) {
  return request<SkillRepositorySetupResponse>("/local-settings/create-local", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function createHumanReviewTemplate() {
  return request<HumanReviewTemplateResponse>("/human-review-template", {
    method: "POST",
  })
}

export function fetchHumanReviewTemplate() {
  return request<HumanReviewTemplateResponse>("/human-review-template")
}

export function updateHumanReviewTemplate(items: HumanReviewItem[]) {
  return request<HumanReviewTemplateResponse>("/human-review-template", {
    method: "PUT",
    body: JSON.stringify({ items }),
  })
}

export function fetchModelStatus() {
  return request<ModelRuntimeStatus>("/model-status")
}

export function warmupModels(payload: {
  run_asr: boolean
  run_ocr: boolean
  execute: boolean
}) {
  return request<ModelWarmupResponse>("/model-warmup", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function submitLinkTask(url: string) {
  return request<LinkTaskResponse>("/link-task", {
    method: "POST",
    body: JSON.stringify({ url }),
  })
}

export function fetchLinkDiagnostics(limit = 20) {
  return request<LinkDiagnosticRecord[]>(
    `/link-diagnostics?limit=${encodeURIComponent(String(limit))}`,
  )
}

export function analyzeText(payload: {
  title: string
  content: string
  input_type: "subtitle" | "transcript" | "text"
  url?: string
  source_video_id?: string
  author?: string | null
  publish_time?: string | null
  source_created_at?: string
  asr_text?: string
  ocr_text?: string
  transcript_source?: string
  transcript_confidence?: number
}) {
  return request<AnalyzeTextResponse>("/analyze-text", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function analyzeInspiration(payload: {
  title: string
  content: string
  input_type: "subtitle" | "transcript" | "text"
  url?: string
}) {
  return request<AnalyzeTextResponse>("/inspirations/analyze", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function uploadText(payload: UploadTextPayload) {
  return request<AnalyzeTextResponse>("/upload-text", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function uploadVideo(file: File, runExtractors = false) {
  const response = await fetch(
    `${API_BASE}/api/v1/script-workbench/upload-video?file_name=${encodeURIComponent(file.name)}&run_extractors=${runExtractors ? "true" : "false"}`,
    {
      method: "POST",
      headers: {
        "Content-Type": file.type || "application/octet-stream",
        ...authorizationHeader(),
      },
      body: file,
    },
  )

  if (!response.ok) {
    const message = await readApiErrorMessage(
      response,
      `视频上传失败：${response.status}`,
    )
    throw new WorkbenchApiError(message, response.status)
  }

  return response.json() as Promise<VideoUploadResponse>
}

export function startVideoExtractionTask(
  sourceVideoId: string,
  payload = { run_asr: true, run_ocr: true },
) {
  return request<VideoExtractionTask>(
    `/video-extraction-tasks/${encodeURIComponent(sourceVideoId)}`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  )
}

export function fetchVideoExtractionTask(taskId: string) {
  return request<VideoExtractionTask>(
    `/video-extraction-tasks/${encodeURIComponent(taskId)}`,
  )
}

export function fetchVideoExtractionTasks(limit = 20) {
  return request<VideoExtractionTask[]>(
    `/video-extraction-tasks?limit=${encodeURIComponent(String(limit))}`,
  )
}

export function cancelVideoExtractionTask(taskId: string) {
  return request<VideoExtractionTask>(
    `/video-extraction-tasks/${encodeURIComponent(taskId)}/cancel`,
    {
      method: "POST",
    },
  )
}

export function retryVideoExtractionTask(taskId: string) {
  return request<VideoExtractionTask>(
    `/video-extraction-tasks/${encodeURIComponent(taskId)}/retry`,
    {
      method: "POST",
    },
  )
}

export function generateHotspot(payload: {
  hotspot: string
  account_type: string
  template_id?: string
  duration_seconds: number
  tone: string
  goal: string
}) {
  return request<GenerateHotspotResponse>("/generate-hotspot", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function diagnoseDraft(payload: DraftInputPayload) {
  return request<DraftDiagnosis>("/drafts/diagnose", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function matchDraftSkills(payload: DraftRewritePayload) {
  return request<SkillMatch[]>("/drafts/match-skills", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function rewriteDraft(payload: DraftRewritePayload) {
  return request<DraftRewriteResponse>("/drafts/rewrite", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function startDraftRewriteTask(payload: DraftRewritePayload) {
  return request<DraftRewriteTask>("/drafts/rewrite-tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function fetchDraftRewriteTask(taskId: string) {
  return request<DraftRewriteTask>(
    `/drafts/rewrite-tasks/${encodeURIComponent(taskId)}`,
  )
}

export function rewriteScriptSelection(payload: SelectionRewritePayload) {
  return request<SelectionRewriteResponse>("/scripts/selection-rewrite", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function fetchSelectionRewriteSuggestions(
  payload: SelectionRewriteSuggestionPayload,
) {
  return request<SelectionRewriteSuggestionResponse>(
    "/scripts/selection-rewrite-suggestions",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  )
}

export function updateTemplateReview(
  templateId: string,
  payload: TemplateReviewPayload,
) {
  return request<TemplatePattern>(
    `/templates/${encodeURIComponent(templateId)}/review`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  )
}

export function updateSkillGovernance(
  templateId: string,
  payload: SkillGovernancePayload,
) {
  return request<TemplatePattern>(`/writing-skills/${templateId}/governance`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
}

export function approveAndPublishWritingSkill(
  templateId: string,
  payload: SkillGovernancePayload,
) {
  return request<SkillApprovalAndPublishResponse>(
    `/writing-skills/${encodeURIComponent(templateId)}/approve-and-publish`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  )
}

export function fetchSkillPromotionReadiness(templateId: string) {
  return request<SkillPromotionReadiness>(
    `/writing-skills/${encodeURIComponent(templateId)}/promotion-readiness`,
  )
}

export function runSkillReleaseEvaluation() {
  return request<SkillReleaseEvaluationResponse>("/skill-release-evaluation", {
    method: "POST",
  })
}

export function createWritingPreset(payload: WritingPresetCreatePayload) {
  return request<TemplatePattern>("/writing-presets", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function createWritingSkill(payload: WritingPresetCreatePayload) {
  return request<TemplatePattern>("/writing-skills", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function updateGeneratedScript(
  scriptId: string,
  payload: GeneratedScriptUpdatePayload,
) {
  return request<GeneratedScript>(`/scripts/${encodeURIComponent(scriptId)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
}

export function copyGeneratedScriptVersion(
  scriptId: string,
  versionId: string,
) {
  return request<GeneratedScript>(
    `/scripts/${encodeURIComponent(scriptId)}/versions/${encodeURIComponent(versionId)}/copy`,
    { method: "POST" },
  )
}

export function copyGeneratedScript(scriptId: string) {
  return request<GeneratedScript>(
    `/scripts/${encodeURIComponent(scriptId)}/copy`,
    { method: "POST" },
  )
}
