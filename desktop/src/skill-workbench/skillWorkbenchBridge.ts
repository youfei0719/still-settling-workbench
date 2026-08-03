import { invoke } from "@tauri-apps/api/core"
import type {
  CandidateEvidence,
  DiagnosticLog,
  DepositSession,
  LocalSettings,
  LocalCandidate,
  MediaExtractionResult,
  MediaProgress,
  ModelEvaluation,
  PublishProgress,
  ProviderModels,
  PublishResult,
  RepositorySetupRequest,
  RuntimeHealth,
  StableRepositorySnapshot,
  SettingsUpdate,
  SourceRecord,
  StructureDraft,
  StructureRemediation,
  TranscriptProofreadResult,
} from "./types"

export interface PersistedWorkbenchState {
  session: DepositSession
  candidates: LocalCandidate[]
}

const browserDiagnosticLogs: DiagnosticLog[] = []

function normalizedDiagnosticLog(log: Partial<DiagnosticLog>): DiagnosticLog {
  return {
    id: log.id ?? `diagnostic-${crypto.randomUUID()}`,
    traceId: log.traceId ?? `ui-${crypto.randomUUID()}`,
    action: log.action ?? "ui.unknown",
    stage: log.stage ?? "interaction",
    status: log.status ?? "info",
    code: log.code ?? "UI_EVENT",
    message: log.message ?? "界面行为已记录",
    location: log.location ?? "SkillWorkbench.tsx",
    detail: log.detail ?? null,
    createdAt: log.createdAt ?? new Date().toISOString(),
  }
}

export function isNativeDesktop() {
  return "__TAURI_INTERNALS__" in window || window.location.protocol === "tauri:"
}

function legacyEvidence(candidate: Partial<LocalCandidate>, session: Partial<DepositSession>): CandidateEvidence[] {
  const source = session.source
  if (!source) return []
  const normalizedSource: SourceRecord = {
    ...source,
    id: source.id ?? `source-${source.createdAt ?? Date.now()}`,
  } as SourceRecord
  return [{
    id: `evidence-legacy-${candidate.id ?? Date.now()}`,
    source: normalizedSource,
    transcript: session.transcript ?? "",
    fingerprint: `legacy-${candidate.id ?? Date.now()}`,
    addedAt: candidate.updatedAt ?? new Date().toISOString(),
  }]
}

function normalizeState(value: Partial<PersistedWorkbenchState>): PersistedWorkbenchState | null {
  if (!value.session) return null
  // targetCandidateId belonged to the retired multi-source supplement flow.
  // Deliberately discard it while loading old local state.
  const { targetCandidateId: _legacyTargetCandidateId, ...sessionValue } = value.session as DepositSession & { targetCandidateId?: unknown }
  const session: DepositSession = {
    ...sessionValue,
    source: sessionValue.source ? {
      ...sessionValue.source,
      id: sessionValue.source.id ?? `source-${sessionValue.source.createdAt ?? Date.now()}`,
    } : null,
    events: sessionValue.events ?? [],
    proofread: sessionValue.proofread ?? null,
  } as DepositSession
  const candidates = (value.candidates ?? []).map((candidate) => {
    const partial = candidate as Partial<LocalCandidate> & { status?: string }
    const sources = partial.sources?.length ? partial.sources : legacyEvidence(partial, session)
    return {
      ...partial,
      sources,
      sourceCount: sources.length || partial.sourceCount || 1,
      status: ["collecting", "review_ready", "release_ready", "exported"].includes(partial.status ?? "")
        ? partial.status
        : "collecting",
      modelEvaluation: partial.modelEvaluation ?? null,
      humanReview: partial.humanReview ?? null,
      release: partial.release ?? null,
    } as LocalCandidate
  })
  return { session, candidates }
}

export const skillWorkbenchBridge = {
  async recordDiagnosticLog(log: Partial<DiagnosticLog>): Promise<DiagnosticLog> {
    const normalized = normalizedDiagnosticLog(log)
    if (isNativeDesktop()) return invoke<DiagnosticLog>("record_diagnostic_log", { log: normalized })
    browserDiagnosticLogs.unshift(normalized)
    return normalized
  },

  async listDiagnosticLogs(limit = 100): Promise<DiagnosticLog[]> {
    if (isNativeDesktop()) return invoke<DiagnosticLog[]>("list_diagnostic_logs", { limit })
    return browserDiagnosticLogs.slice(0, limit)
  },

  async clearDiagnosticLogs(): Promise<void> {
    if (isNativeDesktop()) {
      await invoke("clear_diagnostic_logs")
      return
    }
    browserDiagnosticLogs.splice(0, browserDiagnosticLogs.length)
  },

  async load(): Promise<PersistedWorkbenchState | null> {
    if (isNativeDesktop()) {
      const saved = await invoke<Partial<PersistedWorkbenchState> | null>("load_skill_workbench_state")
      return saved ? normalizeState(saved) : null
    }
    return null
  },

  async save(state: PersistedWorkbenchState): Promise<void> {
    if (isNativeDesktop()) {
      await invoke("save_skill_workbench_state", { state })
      return
    }
    void state
  },

  async selectLocalMedia(browserFile?: File): Promise<SourceRecord | null> {
    if (!isNativeDesktop()) {
      if (!browserFile) return null
      return {
        id: `source-${crypto.randomUUID()}`,
        mode: "local_media",
        label: browserFile.name,
        value: browserFile.name,
        authorized: true,
        mediaLocalOnly: true,
        createdAt: new Date().toISOString(),
      }
    }
    const { open } = await import("@tauri-apps/plugin-dialog")
    const selected = await open({
      multiple: false,
      directory: false,
      filters: [{ name: "视频或音频", extensions: ["mp4", "mov", "m4v", "webm", "mp3", "m4a", "wav", "aac", "flac"] }],
    })
    if (typeof selected !== "string") return null
    const tasks = await invoke<Array<{ id: string; media: { fileName: string; path: string } }>>("import_media", { paths: [selected] })
    const task = tasks[0]
    if (!task) return null
    return {
      id: task.id,
      mode: "local_media",
      label: task.media.fileName,
      value: task.media.path,
      authorized: true,
      mediaLocalOnly: true,
      createdAt: new Date().toISOString(),
    }
  },

  async runtimeHealth(): Promise<RuntimeHealth> {
    if (isNativeDesktop()) return invoke<RuntimeHealth>("runtime_health")
    return {
      mode: "browser",
      database: "unavailable",
      mediaPipeline: {
        status: "unavailable",
        label: "浏览器预览不运行本机媒体链",
        version: "not-available",
        protocolVersion: "native-v1",
      },
      credentialStore: "unavailable",
      stableSnapshot: null,
      stableSnapshotError: "浏览器只读预览，未运行 Tauri 仓库校验",
      checkedAt: new Date().toISOString(),
    }
  },

  async loadStableRepositorySnapshot(): Promise<StableRepositorySnapshot> {
    if (isNativeDesktop()) return invoke<StableRepositorySnapshot>("load_stable_repository_snapshot")
    return {
      configured: false, verified: false, hasStable: false, version: null, updatedAt: null,
      packagePath: null, manifestPath: null, repositoryPath: null, remoteUrl: null, branch: null,
      skills: [], runtimeFiles: {}, error: "浏览器只读预览，未连接真实仓库", preview: true,
    }
  },

  async latestPublishJob(candidateId: string): Promise<PublishResult | null> {
    if (!isNativeDesktop()) return null
    return invoke<PublishResult | null>("latest_publish_job", { candidateId })
  },

  async processMedia(mode: "douyin_link" | "local_media", input: string): Promise<MediaExtractionResult> {
    if (!isNativeDesktop()) throw new Error("真实下载与转写只在 Mac / Windows 桌面端可用")
    return invoke<MediaExtractionResult>("process_media_source", { request: { mode, input } })
  },

  async analyzeTranscript(request: { title: string; transcript: string; sourceUrl?: string }): Promise<StructureDraft> {
    if (!isNativeDesktop()) throw new Error("真实模型拆解只在 Mac / Windows 桌面端可用")
    return invoke<StructureDraft>("analyze_transcript", { request })
  },

  async proofreadTranscript(transcript: string): Promise<TranscriptProofreadResult> {
    if (!isNativeDesktop()) throw new Error("真实模型校对只在 Mac / Windows 桌面端可用")
    return invoke<TranscriptProofreadResult>("proofread_transcript", { request: { transcript } })
  },

  async evaluateCandidate(candidate: LocalCandidate): Promise<ModelEvaluation> {
    if (!isNativeDesktop()) throw new Error("真实模型评测只在 Mac / Windows 桌面端可用")
    return invoke<ModelEvaluation>("evaluate_candidate", { candidate })
  },

  async remediateCandidate(candidate: LocalCandidate): Promise<StructureRemediation> {
    if (!isNativeDesktop()) throw new Error("AI 修复只在 Mac / Windows 桌面端可用")
    return invoke<StructureRemediation>("remediate_candidate", { candidate })
  },

  async getSettings(): Promise<LocalSettings | null> {
    if (!isNativeDesktop()) return null
    return invoke<LocalSettings>("get_local_settings")
  },

  async updateSettings(update: SettingsUpdate): Promise<LocalSettings> {
    if (!isNativeDesktop()) throw new Error("本机设置只在 Mac / Windows 桌面端可用")
    return invoke<LocalSettings>("update_local_settings", { update })
  },

  async listProviderModels(): Promise<ProviderModels> {
    if (!isNativeDesktop()) throw new Error("模型连接只在 Mac / Windows 桌面端可用")
    return invoke<ProviderModels>("list_provider_models")
  },

  async testModelConnection(): Promise<{ passed: boolean; model: string; message: string }> {
    if (!isNativeDesktop()) throw new Error("模型连接只在 Mac / Windows 桌面端可用")
    return invoke("test_model_connection")
  },

  async setupRepository(request: RepositorySetupRequest): Promise<{ message: string; repositoryPath: string; remoteUrl: string; settings: LocalSettings }> {
    if (!isNativeDesktop()) throw new Error("项目配置只在 Mac / Windows 桌面端可用")
    return invoke("setup_skill_repository", { request })
  },

  async publishReleaseCandidate(candidateId: string): Promise<PublishResult> {
    if (!isNativeDesktop()) throw new Error("stable 发布只在 Mac / Windows 桌面端可用")
    return invoke<PublishResult>("publish_release_candidate", { candidateId })
  },

  async onMediaProgress(handler: (progress: MediaProgress) => void): Promise<() => void> {
    if (!isNativeDesktop()) return () => undefined
    const { listen } = await import("@tauri-apps/api/event")
    return listen<MediaProgress>("media-progress", (event) => handler(event.payload))
  },

  async onPublishProgress(handler: (progress: PublishProgress) => void): Promise<() => void> {
    if (!isNativeDesktop()) return () => undefined
    const { listen } = await import("@tauri-apps/api/event")
    return listen<PublishProgress>("publish-progress", (event) => handler(event.payload))
  },
}
