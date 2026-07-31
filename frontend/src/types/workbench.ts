export type TaskStatus =
  | "pending"
  | "processing"
  | "completed"
  | "needs_upload"
  | "failed"
  | "cancelled"
export type InputType =
  | "douyin_url"
  | "video"
  | "subtitle"
  | "transcript"
  | "text"
export type RiskLevel = "low" | "medium" | "high"
export type ScriptProductionStatus =
  | "draft"
  | "editing"
  | "review_ready"
  | "exported"
export type SkillStatus = "candidate" | "active" | "paused" | "retired"

export interface SourceVideo {
  id: string
  input_type: InputType
  title: string
  url?: string | null
  author?: string | null
  publish_time?: string | null
  status: TaskStatus
  material_path?: string | null
  created_at: string
}

export interface Transcript {
  id: string
  source_video_id: string
  asr_text: string
  ocr_text: string
  content_text: string
  timestamps: string[]
  confidence: number
  source: string
}

export interface TranscriptCorrection {
  original: string
  corrected: string
  reason: string
  confidence: number
}

export interface ScriptSegment {
  name: string
  start: string
  duration: string
  summary: string
}

export interface ScriptAnalysis {
  id: string
  source_video_id: string
  hook: string
  conflict: string
  structure: ScriptSegment[]
  emotion_curve: string[]
  reversal: string
  ending_cta: string
  account_type: string
  reusable_template: string
  template_suggestions: string[]
  content_angle: string
}

export interface SkillSourceRecord {
  source_video_id: string
  source_analysis_id?: string | null
  title: string
  author?: string | null
  url?: string | null
  transcript: string
  recognized_at?: string | null
}

export interface SkillEvidence {
  id?: string
  claim: string
  source_title: string
  source_url: string
  source_type?: string
  evidence_tier: "A" | "B" | "C"
  quote?: string
  scope: "structure" | "fact"
  checked_at?: string
}

export interface SkillEvaluationSummary {
  routing_accuracy?: number | null
  no_match_accuracy?: number | null
  safety_block_rate?: number | null
  citation_coverage?: number | null
  human_score?: number | null
  minimum_dimension_score?: number | null
  passed: boolean
  report_path?: string | null
  evaluated_at?: string | null
}

export interface SkillReviewRecord {
  id?: string
  reviewer?: string
  blind_label?: string
  accuracy: number
  structure: number
  douyin_fit: number
  shootability: number
  distinctiveness: number
  approved: boolean
  note?: string
  created_at?: string
}

export interface TemplatePattern {
  id: string
  name: string
  account_type: string
  hotspot_types: string[]
  solves_problems?: string[]
  match_signals?: string[]
  applicable_scenes?: string[]
  unsuitable_scenes?: string[]
  skeleton: string[]
  hook_formula: string
  emotion_rhythm: string
  ending_formula: string
  risk_boundary: string
  quality_score?: number
  usage_count: number
  disabled_reason?: string | null
  last_review_note?: string | null
  source_analysis_id?: string | null
  source_titles?: string[]
  sources?: SkillSourceRecord[]
  source_count?: number
  pattern_fingerprint?: string
  status?: SkillStatus
  version?: number
  owner?: string
  platforms?: string[]
  reviewed_at?: string | null
  expires_at?: string | null
  required_inputs?: string[]
  output_contract?: string[]
  promotion_reason?: string | null
  evidence?: SkillEvidence[]
  evaluation_summary?: SkillEvaluationSummary
  reviews?: SkillReviewRecord[]
  created_at?: string | null
}

export interface CodexSkillPackResponse {
  skill_name: string
  version: string
  generated_at: string
  active_skill_count: number
  total_skill_count: number
  source_count: number
  sync_contract: string
  install_hint: string
  install_manifest: { managed_directories?: string[]; installer?: string }
  files: Record<string, string>
}

export interface CodexSkillPublishResponse {
  status: "published" | "unchanged"
  repository: string
  url: string
  branch: string
  version: string
  commit_sha?: string | null
  message: string
  files_changed: number
}

export interface SkillApprovalAndPublishResponse {
  skill: TemplatePattern
  publish: CodexSkillPublishResponse
}

export interface PresetDraft {
  id: string
  draft_status: "draft"
  source_analysis_id: string
  source_video_id: string
  source_title: string
  source_author?: string | null
  source_url?: string | null
  source_transcript?: string
  source_recognized_at?: string | null
  name: string
  account_type: string
  hotspot_types: string[]
  solves_problems?: string[]
  match_signals?: string[]
  applicable_scenes?: string[]
  unsuitable_scenes?: string[]
  skeleton: string[]
  hook_formula: string
  emotion_rhythm: string
  ending_formula: string
  risk_boundary: string
  borrowable_moves: string[]
  pattern_fingerprint?: string
  similar_skill_id?: string | null
  similar_skill_name?: string | null
  similarity_score?: number
  created_at: string
}

export interface RiskItem {
  label: string
  level: RiskLevel
  reason: string
  rewrite: string
}

export interface RiskCheck {
  passed: boolean
  level: RiskLevel
  items: RiskItem[]
}

export interface GeneratedScript {
  id: string
  title: string
  account_type: string
  content_angle: string
  duration_seconds: number
  spoken_script: string
  shot_suggestions: string[]
  subtitle_rhythm: string[]
  comment_cta: string
  risk_check: RiskCheck
  template_used: string
  preset_application?: string[]
  production_status?: ScriptProductionStatus
  version_label?: string
  editor_note?: string | null
  updated_at?: string | null
  version_history?: GeneratedScriptVersion[]
}

export interface GeneratedScriptVersion {
  id: string
  source_script_id: string
  title: string
  spoken_script: string
  shot_suggestions: string[]
  subtitle_rhythm: string[]
  comment_cta: string
  production_status: ScriptProductionStatus
  version_label: string
  editor_note?: string | null
  created_at: string
}

export interface HotspotBrief {
  id: string
  event_summary: string
  controversy: string
  audience_emotion: string
  angles: string[]
  no_go_zones: string[]
}

export interface WorkbenchOverview {
  tasks: {
    processing: number
    queued: number
    completed: number
    failed: number
  }
  templates: TemplatePattern[]
  recent_analyses: ScriptAnalysis[]
  generated_scripts: GeneratedScript[]
}

export interface LlmRuntimeConfig {
  mode: "offline" | "optional" | "required"
  model: string
  api_base?: string | null
  temperature: number
  max_retries: number
}

export interface WorkbenchCapability {
  key: string
  label: string
  available: boolean
  status: "ready" | "missing" | "reserved"
  detail: string
}

export interface WorkbenchCapabilities {
  items: WorkbenchCapability[]
  ready_count: number
  total_count: number
}

export interface ExternalGateItem {
  key: "link" | "llm" | "human_review"
  label: string
  passed: boolean
  status: string
  detail: string
  action_items: string[]
}

export interface ExternalGateReport {
  passed: boolean
  items: ExternalGateItem[]
  link_gate: Record<string, unknown>
  llm_gate: Record<string, unknown>
  human_review_gate: Record<string, unknown>
  report_path: string
}

export interface HumanReviewItem {
  id: string
  hotspot: string
  script_title: string
  shootable: boolean
  not_pure_rewrite: boolean
  clear_structure: boolean
  risk_passed: boolean
  reviewer: string
  notes: string
}

export interface HumanReviewTemplateResponse {
  path: string
  required_count: number
  items: HumanReviewItem[]
  message: string
}

export interface LocalSettingsStatus {
  llm_mode: "offline" | "optional" | "required"
  llm_model: string
  llm_api_base: string
  skill_repository_path: string
  skill_remote: string
  skill_remote_url: string
  skill_branch: string
  skill_sync_mode: "github" | "local"
  sources: Record<string, "environment" | "local" | "default">
  llm_api_key_configured: boolean
  llm_api_key_source: "environment" | "keyring" | "session" | "none"
  douyin_cookie_configured: boolean
  douyin_cookie_source: "environment" | "keyring" | "session" | "none"
  secret_storage: "system_keyring" | "session_only"
  secrets_persisted: boolean
  publish_configured: boolean
  message: string
}

export interface LocalSettingsUpdatePayload {
  llm_mode?: "offline" | "optional" | "required"
  llm_model?: string | null
  llm_api_base?: string | null
  llm_api_key?: string | null
  douyin_cookie_string?: string | null
  skill_repository_path?: string | null
  skill_remote?: string | null
  skill_remote_url?: string | null
  skill_branch?: string | null
  skill_sync_mode?: "github" | "local" | null
  clear_llm_key?: boolean
  clear_douyin_cookie?: boolean
}

export interface ModelCatalogItem {
  id: string
  recommended: boolean
  recommendation_reason: string
}

export interface ModelCatalogResponse {
  models: ModelCatalogItem[]
  recommended_model: string
  message: string
}

export interface ModelConnectionCheckResponse {
  passed: boolean
  message: string
}

export interface SkillRepositorySetupResponse {
  settings: LocalSettingsStatus
  message: string
}

export interface LocalSettingsVerification {
  publish_ready: boolean
  git_available: boolean
  gh_authenticated: boolean
  repository_valid: boolean
  remote_matches: boolean
  branch_exists: boolean
  action_items: string[]
  message: string
}

export interface ModelRuntimeItem {
  key: "asr" | "ocr"
  label: string
  available: boolean
  mode: "auto" | "off" | "required"
  initialized: boolean
  status: "ready" | "not_loaded" | "disabled" | "missing" | "failed"
  detail: string
  action_items: string[]
}

export interface ModelRuntimeStatus {
  items: ModelRuntimeItem[]
  ready_count: number
  total_count: number
  message: string
}

export interface ModelWarmupResponse {
  items: ModelRuntimeItem[]
  executed: boolean
  message: string
}

export interface AnalyzeTextResponse {
  source_video: SourceVideo
  transcript: Transcript
  analysis: ScriptAnalysis
  preset_draft: PresetDraft
  risk_check: RiskCheck
  generated_preview: GeneratedScript
  export_markdown: string
  export_json: Record<string, unknown>
}

export interface LinkTaskResponse {
  source_video: SourceVideo
  parser_status: "completed" | "skipped" | "failed"
  parser_provider: string
  output_dir?: string | null
  downloaded_files: string[]
  video_upload?: VideoUploadResponse | null
  parser_error_code?:
    | "downloader_disabled"
    | "downloader_missing"
    | "public_access_unavailable"
    | "cookie_required"
    | "timeout"
    | "no_media"
    | "transcript_quality"
    | "unknown"
    | null
  parser_error_title?: string | null
  parser_error_detail?: string | null
  parser_action_items: string[]
  message: string
  fallback_inputs: string[]
}

export interface LinkDiagnosticRecord {
  id: string
  url: string
  source_video_id: string
  parser_status: "completed" | "skipped" | "failed"
  parser_provider: string
  parser_error_code?:
    | "downloader_disabled"
    | "downloader_missing"
    | "public_access_unavailable"
    | "cookie_required"
    | "timeout"
    | "no_media"
    | "transcript_quality"
    | "unknown"
    | null
  parser_error_title?: string | null
  parser_error_detail?: string | null
  parser_action_items: string[]
  fallback_inputs: string[]
  output_dir?: string | null
  downloaded_file_count: number
  has_video_upload: boolean
  cookie_configured: boolean
  downloader_mode: "auto" | "off" | "required"
  recommended_next_step: string
  message: string
  created_at: string
}

export interface VideoUploadResponse {
  source_video: SourceVideo
  audio_path?: string | null
  frame_paths: string[]
  extraction_status: "completed" | "skipped" | "failed"
  asr_status: "completed" | "skipped" | "failed"
  asr_provider: string
  asr_text: string
  ocr_status: "completed" | "skipped" | "failed"
  ocr_provider: string
  ocr_text: string
  transcript?: Transcript | null
  correction_status: "completed" | "needs_review" | "skipped" | "failed"
  corrections: TranscriptCorrection[]
  unresolved_fragments: string[]
  transcript_quality_score: number
  transcript_quality_message: string
  context_terms: string[]
  message: string
  asr_message: string
  ocr_message: string
  next_step: string
  fallback_inputs: string[]
  media_cleanup_status: "retained" | "completed" | "failed"
  media_cleanup_message: string
}

export interface VideoExtractionTask {
  id: string
  source_video_id: string
  status: "queued" | "processing" | "completed" | "failed" | "cancelled"
  stage: string
  stage_detail: string
  progress: number
  source_video: SourceVideo
  audio_path?: string | null
  frame_paths: string[]
  asr_status: "completed" | "skipped" | "failed"
  asr_message: string
  ocr_status: "completed" | "skipped" | "failed"
  ocr_message: string
  transcript?: Transcript | null
  video_upload?: VideoUploadResponse | null
  error?: string | null
  cancel_requested: boolean
  retry_of?: string | null
  run_asr: boolean
  run_ocr: boolean
  next_step: string
  fallback_inputs: string[]
  media_cleanup_status: "retained" | "completed" | "failed"
  media_cleanup_message: string
  created_at: string
  updated_at: string
}

export interface UploadTextPayload {
  file_name: string
  content: string
  input_type: "subtitle" | "transcript" | "text"
  title?: string
}

export interface GenerateHotspotResponse {
  brief: HotspotBrief
  matched_templates: TemplatePattern[]
  scripts: GeneratedScript[]
}

export type DraftInputType = "hotspot" | "outline" | "partial_script" | "script"

export interface DraftInputPayload {
  title: string
  content: string
  input_type: DraftInputType
  account_type: string
  duration_seconds: number
  tone: string
  goal: string
}

export interface DraftDiagnosis {
  id: string
  draft_title: string
  draft_type: DraftInputType
  strengths: string[]
  problems: string[]
  rewrite_goals: string[]
  suggested_skill_types: string[]
  no_go_zones: string[]
}

export interface SkillMatch {
  skill: TemplatePattern
  match_score: number
  reason: string
  apply_plan: string[]
}

export interface DraftRewritePayload extends DraftInputPayload {
  skill_ids: string[]
}

export interface FactSource {
  title: string
  url: string
  publisher: string
  published_at?: string | null
}

export interface FactVerification {
  required: boolean
  verdict: "not_required" | "verified" | "refuted" | "uncertain" | "failed"
  claim: string
  summary: string
  verified_facts: string[]
  corrections: string[]
  sources: FactSource[]
  checked_at?: string | null
}

export interface DraftRewriteResponse {
  diagnosis: DraftDiagnosis
  matched_skills: SkillMatch[]
  rewrite_plan: string[]
  scripts: GeneratedScript[]
  generation_mode?: "ai" | "fallback" | "blocked"
  generation_model?: string | null
  generation_note?: string
  fact_verification: FactVerification
}

export interface DraftRewriteTask {
  id: string
  status: "queued" | "processing" | "completed" | "failed"
  stage:
    | "queued"
    | "diagnosing"
    | "fact_checking"
    | "matching_skill"
    | "generating_scripts"
    | "quality_checking"
    | "completed"
    | "failed"
  stage_detail: string
  progress: number
  timeout_seconds: number
  activities: DraftRewriteActivity[]
  result?: DraftRewriteResponse | null
  error?: string | null
  created_at: string
  updated_at: string
}

export interface DraftRewriteActivity {
  id: string
  phase: "diagnosis" | "research" | "skill_match" | "writing" | "quality"
  kind: "status" | "search" | "source" | "skill" | "draft" | "check"
  title: string
  detail: string
  status: "active" | "completed" | "failed"
  created_at: string
}

export interface SelectionRewritePayload {
  selected_text: string
  instruction: string
  full_script: string
  account_type: string
  duration_seconds: number
  tone: string
  skill_name: string
  verified_facts: string[]
  verified_sources: FactSource[]
  rewrite_intents: string[]
  research_mode: "none" | "targeted"
  emotional_goal: string
}

export interface SelectionRewriteResponse {
  replacement: string
  change_summary: string
  supporting_facts: string[]
  sources: FactSource[]
}

export interface SelectionRewriteSuggestionPayload {
  selected_text: string
  full_script: string
  account_type: string
  duration_seconds: number
  tone: string
  skill_name: string
  verified_facts: string[]
}

export interface SelectionRewriteSuggestion {
  id: string
  label: string
  instruction: string
  reason: string
  evidence_needed: boolean
}

export interface SelectionRewriteSuggestionResponse {
  suggestions: SelectionRewriteSuggestion[]
}

export interface TemplateReviewPayload {
  quality_score: number
  applicable_scenes: string[]
  unsuitable_scenes: string[]
  disabled_reason?: string | null
  last_review_note?: string | null
}

export interface SkillGovernancePayload {
  status: SkillStatus
  owner: string
  platforms: string[]
  required_inputs: string[]
  output_contract: string[]
  promotion_reason?: string | null
  expires_at?: string | null
  evidence: SkillEvidence[]
  evaluation_summary: SkillEvaluationSummary
  release_report_path?: string | null
  review?: SkillReviewRecord | null
}

export interface SkillPromotionReadiness {
  template_id: string
  ready: boolean
  blockers: string[]
  source_count: number
  required_source_count: number
  evidence_count: number
  has_structure_evidence: boolean
  evaluation_passed: boolean
  main_review_approved: boolean
}

export interface SkillReleaseEvaluationResponse {
  passed: boolean
  report_path: string
  message: string
}

export interface WritingPresetCreatePayload {
  preset_draft: PresetDraft
  name?: string
  quality_score: number
  applicable_scenes: string[]
  unsuitable_scenes: string[]
  last_review_note?: string | null
  merge_target_id?: string | null
  merge_as_new?: boolean
}

export interface GeneratedScriptUpdatePayload {
  title: string
  spoken_script: string
  shot_suggestions: string[]
  subtitle_rhythm: string[]
  comment_cta: string
  production_status: ScriptProductionStatus
  version_label: string
  editor_note?: string | null
}
