import { describe, expect, it } from "vitest"
import type { LocalCandidate, SourceRecord } from "./types"
import {
  candidateGates,
  applyCandidateRemediation,
  applyModelStructure,
  createSourceSession,
  recordHumanReview,
  recordModelEvaluation,
  saveCandidateFromSession,
} from "./workflow"

function source(index: number): SourceRecord {
  return {
    id: `source-${index}`,
    mode: "verified_transcript",
    label: `授权真实稿件 ${index}`,
    value: `verified-${index}`,
    authorized: true,
    mediaLocalOnly: false,
    createdAt: `2026-08-03T00:0${index}:00Z`,
  }
}

function structuredSession(index: number) {
  const verified = {
    ...createSourceSession(source(index), "proofread_ready", `这是第 ${index} 份经授权且经过来源确认的完整真实稿件，正文足够长并且可以追溯到独立来源。`),
    transcriptQuality: "verified" as const,
  }
  return applyModelStructure(verified, {
    name: "跨来源结构",
    purpose: "提炼可复用判断",
    hook: "给出主判断",
    progression: "用多来源例子推进",
    ending: "收束为长期结论",
    riskBoundary: "必须核验事实",
    sourceCount: 1,
  })
}

describe("Skill 沉淀状态机", () => {
  it("没有真实稿件时拒绝结构拆解", () => {
    const blocked = createSourceSession({ ...source(1), mode: "douyin_link", authorized: false }, "transcript_blocked")
    expect(applyModelStructure(blocked, { name: "x", purpose: "x", hook: "x", progression: "x", ending: "x", riskBoundary: "x", sourceCount: 1 })).toEqual(blocked)
  })

  it("单条授权真实稿件即可保存并进入评测", () => {
    const first = saveCandidateFromSession(structuredSession(1))
    expect(first.ok).toBe(true)
    if (!first.ok) return
    expect(first.candidate.sourceCount).toBe(1)
    expect(first.candidate.status).toBe("review_ready")
    expect(candidateGates(first.candidate).sources).toBe(true)
  })

  it("未经校对确认的转写不能进入结构拆解", () => {
    const pending = createSourceSession(source(1), "transcript_ready", "这是一份刚刚取得的真实转写稿件，尚未经过人工确认，不能直接进入结构拆解或候选保存。")
    const attempted = applyModelStructure(pending, { name: "x", purpose: "x", hook: "x", progression: "x", ending: "x", riskBoundary: "x", sourceCount: 1 })
    expect(attempted).toEqual(pending)
    expect(saveCandidateFromSession({ ...pending, draft: { name: "x", purpose: "x", hook: "x", progression: "x", ending: "x", riskBoundary: "x", sourceCount: 1 } }).ok).toBe(false)
  })

  it("每条已确认稿件独立沉淀为一个候选 Skill", () => {
    const first = saveCandidateFromSession(structuredSession(1))
    const second = saveCandidateFromSession(structuredSession(2))
    expect(first.ok).toBe(true)
    expect(second.ok).toBe(true)
    if (!first.ok || !second.ok) return
    expect(first.candidate.id).not.toBe(second.candidate.id)
    expect(first.candidate.sources).toHaveLength(1)
    expect(second.candidate.sources).toHaveLength(1)
  })

  it("单条来源的模型评测和人工主审全部通过后才允许正式版本", () => {
    const candidate = {
      ...(saveCandidateFromSession(structuredSession(1)) as { ok: true; candidate: LocalCandidate }).candidate,
      sourceCount: 1,
      sources: [{
        id: "e-1",
        source: source(1),
        transcript: "真实稿件 1",
        fingerprint: "fingerprint-1",
        addedAt: "2026-08-03T00:01:00Z",
      }],
      status: "review_ready" as const,
    }
    const evaluated = recordModelEvaluation(candidate, {
      status: "passed",
      score: 86,
      evaluator: "text-reviewer-v1",
      summary: "结构跨来源一致，风险边界完整。",
      evaluatedAt: "2026-08-03T01:00:00Z",
    })
    expect(candidateGates(evaluated)).toEqual({ sources: true, model: true, human: false })
    const reviewed = recordHumanReview(evaluated, {
      status: "approved",
      reviewer: "主审 A",
      notes: "已核验真实稿件、结构和风险边界，可以进入正式版本。",
      reviewedAt: "2026-08-03T02:00:00Z",
    })
    expect(candidateGates(reviewed)).toEqual({ sources: true, model: true, human: true })
    expect(reviewed.status).toBe("release_ready")
  })

  it("应用 AI 去特定化草稿后保留来源并重新要求评测", () => {
    const initial = (saveCandidateFromSession(structuredSession(1)) as { ok: true; candidate: LocalCandidate }).candidate
    const evaluated = recordModelEvaluation(initial, {
      status: "failed", score: 76, evaluator: "reviewer", summary: "原稿特定表达过多", evaluatedAt: "2026-08-03T03:00:00Z",
    })
    const remediated = applyCandidateRemediation(evaluated, {
      draft: { ...evaluated, name: "由规则反差切入的公共服务温度叙事", hook: "先用制度边界与人情温度的反差建立判断。", progression: "以多个功能角色递进解释服务如何回应真实处境。", ending: "回到公共系统对普通人处境的长期支持。", sourceCount: 1 },
      preservedIntent: "保留从规则边界进入，再升维到公共服务温度的结构意图。",
      changes: ["移除了原稿专属地名和句式。"],
      provider: "reviewer",
    })
    expect(remediated.id).toBe(initial.id)
    expect(remediated.sources).toEqual(initial.sources)
    expect(remediated.modelEvaluation).toBeNull()
    expect(remediated.humanReview).toBeNull()
    expect(candidateGates(remediated)).toEqual({ sources: true, model: false, human: false })
  })
})
