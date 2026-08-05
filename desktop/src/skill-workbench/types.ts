export type WorkbenchPage = "deposit" | "library" | "diagnostics"

export type SourceMode = "douyin_link" | "local_media" | "verified_transcript"

export type DepositStage =
  | "awaiting_source"
  | "source_verified"
  | "transcript_blocked"
  | "transcript_ready"
  | "proofread_ready"
  | "structure_ready"
  | "candidate_saved"

export interface SourceRecord {
  id: string
  mode: SourceMode
  label: string
  value: string
  authorized: boolean
  mediaLocalOnly: boolean
  createdAt: string
}

export interface StructureDraft {
  name: string
  purpose: string
  hook: string
  progression: string
  ending: string
  riskBoundary: string
  sourceCount: number
}

export interface TranscriptCorrection {
  id: string
  original: string
  replacement: string
  reason: string
  confidence: number
  status: "pending" | "accepted" | "rejected"
}

export interface TranscriptProofreadResult {
  originalTranscript: string
  formattedTranscript: string
  corrections: TranscriptCorrection[]
  uncertainties: string[]
  provider: string
}

export interface DepositSession {
  stage: DepositStage
  source: SourceRecord | null
  transcript: string
  transcriptQuality: "unavailable" | "verified" | "needs_review"
  proofread: TranscriptProofreadResult | null
  draft: StructureDraft | null
  events: Array<{ id: string; label: string; detail: string; at: string }>
}

export interface CandidateEvidence {
  id: string
  source: SourceRecord
  transcript: string
  proofread?: TranscriptProofreadResult | null
  fingerprint: string
  addedAt: string
}

export interface ModelEvaluation {
  status: "passed" | "failed"
  score: number
  evaluator: string
  summary: string
  evaluatedAt: string
}

export interface StructureRemediation {
  draft: StructureDraft
  preservedIntent: string
  changes: string[]
  provider: string
}

export interface HumanReview {
  status: "approved" | "changes_requested"
  reviewer: string
  notes: string
  reviewedAt: string
}

export interface ReleaseExport {
  version: string
  path: string
  exportedAt: string
}

export type CandidateStatus = "collecting" | "review_ready" | "release_ready" | "exported"

export interface LocalCandidate extends StructureDraft {
  id: string
  status: CandidateStatus
  sourceLabel: string
  sources: CandidateEvidence[]
  modelEvaluation: ModelEvaluation | null
  humanReview: HumanReview | null
  release: ReleaseExport | null
  updatedAt: string
}

export interface RuntimeHealth {
  mode: "native" | "browser"
  database: "healthy" | "unavailable"
  mediaPipeline: {
    status: "healthy" | "unavailable"
    label: string
    version: string
    protocolVersion: string
  }
  credentialStore: "available_unverified" | "unavailable"
  stableSnapshot?: StableRepositorySnapshot | null
  stableSnapshotError?: string | null
  checkedAt: string
}

export interface StableRepositorySnapshot {
  configured: boolean
  verified: boolean
  hasStable: boolean
  version: string | null
  updatedAt: string | null
  packagePath: string | null
  manifestPath: string | null
  repositoryPath: string | null
  remoteUrl: string | null
  branch: string | null
  skills: Array<Record<string, unknown>>
  runtimeFiles: Record<string, string>
  error: string | null
  preview?: boolean
}

export interface PublishJob {
  id: string
  candidateId: string
  version: string
  status: "pending" | "running" | "succeeded" | "failed"
  stage: "pending" | "loading_base" | "building" | "validating" | "committing" | "fetching" | "rebasing" | "pushing" | "verifying" | "succeeded" | "failed"
  repositoryPath: string
  remoteUrl: string
  remote: string
  branch: string
  packagePath: string | null
  manifestPath: string | null
  commitSha: string | null
  commitUrl: string | null
  startedAt: string
  updatedAt: string
  finishedAt: string | null
  errorCode: string | null
  errorMessage: string | null
  remoteVerifiedAt: string | null
}

export type DiagnosticStatus = "started" | "success" | "error" | "info"

export interface DiagnosticLog {
  id: string
  traceId: string
  action: string
  stage: string
  status: DiagnosticStatus
  code: string
  message: string
  location: string
  detail: string | null
  createdAt: string
}

export interface ToolStatus {
  available: boolean
  version: string
  executablePath?: string | null
}

export interface LocalSettings {
  llmMode: "offline" | "optional" | "required"
  llmModel: string
  llmApiBase: string
  asrModel: string
  asrApiBase: string
  skillSyncMode: "local" | "github"
  skillRepositoryPath: string
  skillRemote: string
  skillRemoteUrl: string
  skillBranch: string
  networkProxy: string
  llmApiKeyConfigured: boolean
  asrApiKeyConfigured: boolean
  asrReady: boolean
  asrBackend: "local_mlx" | "openai_compatible_api"
  douyinCookieConfigured: boolean
  publishConfigured: boolean
  secretStorage: "system_keyring"
  networkProxySource: string
  ytDlp: ToolStatus
  douyinBrowser: ToolStatus
  ffmpeg: ToolStatus
  mlxWhisper: ToolStatus
  git: ToolStatus
  gh: ToolStatus
}

export interface SettingsUpdate {
  llmMode?: LocalSettings["llmMode"]
  llmModel?: string
  llmApiBase?: string
  llmApiKey?: string
  asrModel?: string
  asrApiBase?: string
  asrApiKey?: string
  douyinCookieString?: string
  skillSyncMode?: LocalSettings["skillSyncMode"]
  skillRepositoryPath?: string
  skillRemote?: string
  skillRemoteUrl?: string
  skillBranch?: string
  clearLlmKey?: boolean
  clearAsrKey?: boolean
  clearDouyinCookie?: boolean
  networkProxy?: string
}

export interface MediaExtractionResult {
  taskId: string
  title: string
  url: string | null
  author: string | null
  publishTime: string | null
  transcript: string
  timestamps: Array<Record<string, unknown>>
  provider: string
  mediaCleanupStatus: "completed"
}

export interface MediaProgress {
  taskId: string
  stage: "source" | "download" | "audio" | "transcription" | "cleanup" | "completed"
  message: string
}

export interface ProviderModels {
  models: string[]
  recommendedModel: string
  message: string
}

export interface RepositorySetupRequest {
  mode: "connect" | "create" | "local"
  repositoryUrl?: string
  repositoryName?: string
  visibility?: "private" | "public"
  localParentPath?: string
}

export type PublishResult = PublishJob

export interface PublishProgress {
  stage: PublishJob["stage"]
  message: string
}
