import { describe, expect, it } from "vitest"
import { buildReleasePack } from "./releasePack"
import type { LocalCandidate } from "./types"

const candidate: LocalCandidate = {
  id: "candidate-private-sample",
  name: "反差判断到样本归纳结构",
  purpose: "把已有素材整理成可复用的叙事机制。",
  hook: "先用反差建立注意力。",
  progression: "用可替换模块逐层验证判断。",
  ending: "从个案归纳为普遍认知。",
  riskBoundary: "只使用可核验事实，避免复用原句。",
  sourceLabel: "私有样本标题",
  sourceCount: 1,
  sources: [{
    id: "evidence-private",
    source: { id: "source-private", mode: "douyin_link", label: "私有样本标题", value: "https://v.douyin.com/private/", authorized: true, mediaLocalOnly: false, createdAt: "2026-08-03T00:00:00Z" },
    transcript: "这是一段不能进入发布包的真实稿件。",
    fingerprint: "private-fingerprint",
    addedAt: "2026-08-03T00:00:00Z",
  }],
  status: "release_ready",
  modelEvaluation: { status: "passed", score: 88, evaluator: "test-model", summary: "通过", evaluatedAt: "2026-08-03T00:00:00Z" },
  humanReview: { status: "approved", reviewer: "本机用户", notes: "确认", reviewedAt: "2026-08-03T00:00:00Z" },
  release: null,
  updatedAt: "2026-08-03T00:00:00Z",
}

describe("发布包脱敏", () => {
  it("不写入来源、真实稿件、指纹或本机用户身份", () => {
    const pack = buildReleasePack(candidate, "wb-private-check")
    const content = JSON.stringify(pack)
    expect(content).not.toContain("私有样本标题")
    expect(content).not.toContain("v.douyin.com/private")
    expect(content).not.toContain("不能进入发布包")
    expect(content).not.toContain("private-fingerprint")
    expect(content).not.toContain("本机用户")
  })
})
