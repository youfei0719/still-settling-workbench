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

/** Phase 4：段落 → 素材 / 事实 的对应关系（不进正文）。 */
export interface ScriptEvidenceLink {
  section: string
  material_ids: string[]
  claim_ids: string[]
  note: string
}

export interface MaterialGap {
  gap: string
  handling: string
}

export interface UnsupportedClaim {
  text: string
  reason: string
  action: "removed" | "downgraded" | "kept_as_opinion"
}

export interface EvidenceCheckResult {
  passed: boolean
  unsupported_claims: UnsupportedClaim[]
  notes: string[]
  checked_at?: string | null
}

export interface ScriptGenerationPayload {
  topic: string
  user_material?: string
  selected_angle: string
  angle_name?: string
  structure_id: string
  structure_name: string
  structure_steps: string[]
  structure_mapping: StructureMaterialMapping[]
  structure_gaps: string[]
  materials: MaterialCard[]
  research_brief?: ResearchBrief | null
  account_type: string
  duration_seconds: number
  tone: string
  goal: string
  generation_notes?: string
}

export interface ScriptGenerationResponse {
  script: GeneratedScript
  generation_mode: "ai" | "fallback"
  model?: string | null
  evidence_policy: string[]
  note: string
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
  /** Phase 4：完整成稿的证据追踪。 */
  title_candidates?: string[]
  used_material_ids?: string[]
  used_claim_ids?: string[]
  material_gaps?: MaterialGap[]
  evidence_map?: ScriptEvidenceLink[]
  evidence_check?: EvidenceCheckResult
  structure_coverage?: string[]
  evidence_policy?: string[]
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

export interface ServerMediaTaskResult {
  source_url: string
  title: string
  author?: string | null
  publish_time?: string | null
  transcript: string
  timestamps: string[]
  provider: string
}

export interface ServerMediaTask {
  id: string
  source_url: string
  status: "queued" | "processing" | "completed" | "failed"
  stage: string
  stage_detail: string
  progress: number
  result?: ServerMediaTaskResult | null
  error_code?: string | null
  error?: string | null
  retry_of?: string | null
  created_at: string
  updated_at: string
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

export interface ResearchBrief {
  input_type: string
  user_goal: string
  /**
   * Phase 1: extended in place so the same “研究简报 / Research Brief”
   * can carry everything the creation flow needs. Older responses simply
   * omit these fields, so they are optional on the client.
   */
  summary?: string
  /**
   * Phase 1 修复：默认为 preview（仅整理用户输入，未联网核验）。
   * 只有 Phase 2 真实联网研究取到可靠来源后，才允许显示“已确认事实”。
   */
  verification_status?: "preview" | "partial" | "verified"
  verification_note?: string
  verified_facts: string[]
  /** Phase 3：verified_facts 的可追溯视图（含 source_ids）。 */
  verified_claims?: FactClaim[]
  uncertain_claims?: string[]
  opinions?: string[]
  controversies?: string[]
  audience_sentiment?: string
  candidate_angles?: string[]
  timeline: string[]
  platform_context: string[]
  concrete_details: string[]
  risk_flags: string[]
  research_gap: string[]
  sources: FactSource[]
}

/** WritingProject 创作主线：Phase 1 的步骤（前端临时状态，不落库）。 */
export type WritingProjectStep =
  | "topic"
  | "research"
  | "angle"
  | "material"
  | "structure"
  | "draft"
  | "review"
  | "export"

export interface WritingProjectSettings {
  accountType: string
  durationSeconds: number
  tone: string
  goal: string
}

export interface WritingProjectReviewCheck {
  id: string
  label: string
  checked: boolean
}

/**
 * Phase 1 WritingProject 状态聚合。
 * 复用现有接口返回（PrepareDraftResponse），仅在前端内存中保存；
 * 不新增数据库表，也不改 Alembic。
 */
export interface WritingProjectState {
  id: string
  topic: string
  supplement: string
  createdAt: string
  updatedAt: string
  step: WritingProjectStep
  researchStatus: "idle" | "running" | "done" | "error"
  researchError: string | null
  research: PrepareResearchResponse | null
  /** 角度是强制决策节点：只能“选择推荐角度”或“自定义角度”，必须产生 SelectedAngle。 */
  angleMode: "recommended" | "custom"
  selectedAngleId: string
  customAngle: string
  /** Phase 3：第二轮定向研究状态与素材卡。 */
  materialStatus: "idle" | "running" | "done" | "error"
  materialError: string | null
  materialCards: MaterialCard[]
  materialStopReason: string
  materialGuidance: string
  materialModel?: string | null
  selectedMaterialKeys: string[]
  materialNotes: string
  structureMode: "recommended" | "generic"
  selectedStructureId: string
  /** Phase 3：结构推荐基于 SelectedAngle + SelectedMaterials。 */
  structureRecommendations: StructureRecommendation[]
  structureGeneric: StructureRecommendation | null
  structureNote: string
  structureStatus: "idle" | "loading" | "done" | "error"
  structureError: string | null
  settings: WritingProjectSettings
  draftTitle: string
  draftText: string
  /** Phase 4：完整成稿生成状态与证据追踪。 */
  draftStatus: "idle" | "running" | "done" | "error"
  draftError: string | null
  draftGenerationNote: string
  draftModel?: string | null
  titleCandidates: string[]
  shotSuggestions: string[]
  subtitleRhythm: string[]
  commentCta: string
  usedMaterialIds: string[]
  usedClaimIds: string[]
  materialGaps: MaterialGap[]
  evidenceMap: ScriptEvidenceLink[]
  evidenceCheck: EvidenceCheckResult | null
  structureCoverage: string[]
  draftVersions: Array<{
    id: string
    label: string
    title: string
    text: string
    savedAt: string
  }>
  reviewNotes: string
  reviewChecks: WritingProjectReviewCheck[]
  exportedAt: string | null
}

export interface AngleCandidate {
  id: string
  name: string
  thesis: string
  reason: string
  required_facts: string[]
  risk_notes: string[]
  /** Phase 2：角度卡片新增字段（后端为联网研究输出）。 */
  supporting_materials?: string[]
  missing_materials?: string[]
  overlap_risk?: string
  main_risks?: string[]
  /** Phase 3：分类型的支撑依据。 */
  evidence?: AngleEvidenceBundle
}

export type MaterialType =
  | "fact"
  | "quote"
  | "opinion"
  | "case"
  | "data"
  | "background"
  | "comparison"

/** Phase 3：第二轮 Angle-driven Research 产出的素材卡。 */
export interface MaterialCard {
  id: string
  type: MaterialType
  title: string
  summary?: string
  content: string
  source?: string
  publisher?: string
  published_at?: string | null
  source_url?: string
  verification_status: "verified" | "uncertain" | "preview"
  relevance_to_angle?: string
  suggested_usage?: string
  risk?: string
  selected?: boolean
}

export interface MaterialResearchPayload {
  topic: string
  material_text?: string
  source_url?: string
  account_type: string
  duration_seconds: number
  tone: string
  goal: string
  selected_angle: string
  angle_name?: string
  angle_missing_evidence?: string[]
  research_brief?: ResearchBrief | null
}

export interface MaterialResearchResponse {
  materials: MaterialCard[]
  generation_mode: "ai" | "fallback" | "blocked"
  research_model?: string | null
  guidance: string
  stop_reason: string
  reused_source_count: number
}

export interface StructureMaterialMapping {
  step: string
  material_ids: string[]
  note: string
}

export interface StructureRecommendation {
  id: string
  name: string
  kind: "skill" | "generic"
  skeleton: string[]
  hook_formula: string
  emotion_rhythm: string
  ending_formula: string
  why_fits: string
  material_mapping: StructureMaterialMapping[]
  material_gaps: string[]
  risk_notes: string[]
}

export interface StructureRecommendationPayload {
  topic: string
  selected_angle: string
  materials: MaterialCard[]
  account_type: string
  duration_seconds: number
  tone: string
  goal: string
  research_summary?: string
}

export interface StructureRecommendationResponse {
  recommendations: StructureRecommendation[]
  generic_structure: StructureRecommendation
  generation_mode: "ai" | "fallback"
  model?: string | null
  note: string
}

export interface DraftOutline {
  hook_task: string
  key_facts: string[]
  progression: string[]
  turn: string
  emotion: string
  ending: string
  source_map: string[]
}

export interface SelectionRecord {
  angle_mode: "recommended" | "manual" | "custom" | "none"
  selected_angle: string
  skill_selection_mode: "recommended" | "manual" | "custom"
  primary_skill_id?: string | null
  primary_skill_version?: string | null
  additional_skill_ids: string[]
  user_overrides: string[]
}

export interface PrepareDraftPayload {
  topic: string
  material_text: string
  source_url?: string
  account_type: string
  duration_seconds: number
  tone: string
  goal: string
}

export interface PrepareDraftResponse {
  research_brief: ResearchBrief
  angle_candidates: AngleCandidate[]
  matched_skills: SkillMatch[]
  generation_mode: "ai" | "fallback" | "blocked"
  sources: FactSource[]
}

/**
 * Phase 2：研究阶段响应。只包含研究简报与角度候选，
 * 不包含任何 Skill / 结构匹配（结构匹配推迟到 SelectedAngle 之后）。
 */
export interface PrepareResearchResponse {
  research_brief: ResearchBrief
  angle_candidates: AngleCandidate[]
  generation_mode: "ai" | "fallback" | "blocked"
  research_model?: string | null
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
  material_text?: string
  selected_angle?: string
  angle_mode?: "recommended" | "manual" | "custom" | "none"
  skill_selection_mode?: "recommended" | "manual" | "custom"
  custom_instructions?: string[]
  research_brief?: ResearchBrief | null
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
  /** Phase 3：来源 id，供逐条事实追溯。 */
  id?: string
  title: string
  url: string
  publisher: string
  published_at?: string | null
}

/** 逐条可追溯的事实声明：哪一条事实由哪些来源支持。 */
export interface FactClaim {
  id: string
  claim: string
  source_ids: string[]
  confidence: "high" | "medium" | "low"
  verification_status: "verified" | "uncertain"
  note: string
}

/** Angle 支撑依据按证据类型分开，避免把网友观点当事实。 */
export interface AngleEvidenceBundle {
  verified_fact_ids: string[]
  verified_facts: string[]
  opinions: string[]
  examples: string[]
  missing_evidence: string[]
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
  selected_angle: string
  outline?: DraftOutline | null
  selection_record: SelectionRecord
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
