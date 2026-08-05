import type {
  CandidateEvidence,
  DepositSession,
  HumanReview,
  LocalCandidate,
  ModelEvaluation,
  SourceRecord,
  StructureRemediation,
  StructureDraft,
} from "./types"

function uniqueId(prefix: string) {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
  return `${prefix}-${suffix}`
}

function workflowEvent(label: string, detail: string) {
  return { id: uniqueId("event"), label, detail, at: new Date().toISOString() }
}

function normalized(value: string) {
  return value.trim().replace(/\s+/g, " ").toLocaleLowerCase()
}

export function evidenceFingerprint(source: SourceRecord, transcript: string) {
  const input = `${source.mode}\n${normalized(source.value)}\n${normalized(transcript)}`
  let hash = 2166136261
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16).padStart(8, "0")
}

export function createSourceSession(
  source: SourceRecord,
  stage: DepositSession["stage"],
  transcript = "",
): DepositSession {
  return {
    stage,
    source,
    transcript,
    transcriptQuality: transcript ? "needs_review" : "unavailable",
    proofread: null,
    draft: null,
    events: [
      workflowEvent(
        "来源已记录",
        `${source.label} · ${source.mediaLocalOnly ? "媒体仅在本机处理" : "来源可追溯"}`,
      ),
    ],
  }
}

export function applyModelStructure(session: DepositSession, draft: StructureDraft): DepositSession {
  if (!session.transcript || session.transcriptQuality !== "verified") return session
  return {
    ...session,
    stage: "structure_ready",
    draft: { ...draft, sourceCount: 1 },
    events: [
      ...session.events,
      workflowEvent("通用 Skill 结构已生成", "真实模型已从写法样本中抽象跨题材结构；系统将自动建立候选并评测"),
    ],
  }
}

export function updateStructureDraft(session: DepositSession, patch: Partial<StructureDraft>): DepositSession {
  if (!session.draft) return session
  return { ...session, draft: { ...session.draft, ...patch } }
}

function evidenceFromSession(session: DepositSession): CandidateEvidence | null {
  if (!session.source || !session.transcript || session.transcriptQuality !== "verified") return null
  return {
    id: uniqueId("evidence"),
    source: session.source,
    transcript: session.transcript,
    proofread: session.proofread,
    fingerprint: evidenceFingerprint(session.source, session.transcript),
    addedAt: new Date().toISOString(),
  }
}

export type SaveCandidateResult =
  | { ok: true; session: DepositSession; candidate: LocalCandidate; outcome: "created" }
  | { ok: false; message: string }

export function saveCandidateFromSession(session: DepositSession): SaveCandidateResult {
  if (!session.draft || !session.source) return { ok: false, message: "结构草稿或来源缺失，无法保存候选。" }
  const evidence = evidenceFromSession(session)
  if (!evidence) return { ok: false, message: "只有经确认的真实稿件才能成为候选证据。" }
  const now = new Date().toISOString()

  const candidate: LocalCandidate = {
    ...session.draft,
    id: uniqueId("candidate"),
    sourceLabel: session.source.label,
    sources: [evidence],
    sourceCount: 1,
    status: "review_ready",
    modelEvaluation: null,
    humanReview: null,
    release: null,
    updatedAt: now,
  }
  return {
    outcome: "created",
    candidate,
    session: {
      ...session,
      stage: "candidate_saved",
      events: [...session.events, workflowEvent("Skill 已保存", "已由单条授权真实稿件沉淀为本机 Skill")],
    },
    ok: true,
  }
}

export function candidateGates(candidate: LocalCandidate) {
  return {
    sources: candidate.sourceCount >= 1,
    model: candidate.modelEvaluation?.status === "passed" && candidate.modelEvaluation.score >= 80,
    human: candidate.humanReview?.status === "approved",
  }
}

export function recordModelEvaluation(candidate: LocalCandidate, evaluation: ModelEvaluation): LocalCandidate {
  if (candidate.sourceCount < 1) return candidate
  const passed = evaluation.status === "passed" && evaluation.score >= 80
  return {
    ...candidate,
    modelEvaluation: evaluation,
    humanReview: null,
    release: null,
    status: passed ? "review_ready" : "collecting",
    updatedAt: evaluation.evaluatedAt,
  }
}

export function applyCandidateRemediation(candidate: LocalCandidate, remediation: StructureRemediation): LocalCandidate {
  const now = new Date().toISOString()
  return {
    ...candidate,
    ...remediation.draft,
    id: candidate.id,
    sourceLabel: candidate.sourceLabel,
    sourceCount: candidate.sourceCount,
    sources: candidate.sources,
    modelEvaluation: null,
    humanReview: null,
    release: null,
    status: "review_ready",
    updatedAt: now,
  }
}

export function recordHumanReview(candidate: LocalCandidate, review: HumanReview): LocalCandidate {
  if (!candidateGates(candidate).model) return candidate
  return {
    ...candidate,
    humanReview: review,
    release: null,
    status: review.status === "approved" ? "release_ready" : "review_ready",
    updatedAt: review.reviewedAt,
  }
}

export function markCandidateExported(candidate: LocalCandidate, version: string, path: string): LocalCandidate {
  if (!Object.values(candidateGates(candidate)).every(Boolean)) return candidate
  const exportedAt = new Date().toISOString()
  return {
    ...candidate,
    release: { version, path, exportedAt },
    status: "exported",
    updatedAt: exportedAt,
  }
}
