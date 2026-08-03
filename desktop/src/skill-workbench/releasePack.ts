import repositorySkillData from "virtual:douyin-skill-repository"
import type { LocalCandidate, ReleasePack } from "./types"
import { candidateGates } from "./workflow"

const VERSION_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/

function referenceMarkdown(candidate: LocalCandidate) {
  return `# ${candidate.name}\n\n## 解决什么问题\n\n${candidate.purpose}\n\n## 开头\n\n${candidate.hook}\n\n## 推进\n\n${candidate.progression}\n\n## 收束\n\n${candidate.ending}\n\n## 风险边界\n\n${candidate.riskBoundary}\n\n## 质量证据摘要\n\n- 已确认授权来源数量：${candidate.sourceCount}\n- 模型评测：${candidate.modelEvaluation?.score ?? 0} / 100\n- 最终发布确认：已完成\n\n发布包不包含来源标题、链接、来源指纹、真实稿件、媒体或用户身份。\n`
}

export function suggestedReleaseVersion(candidate: LocalCandidate) {
  const date = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15)
  return `wb-${date}-${candidate.id.slice(-8).replace(/[^A-Za-z0-9]/g, "")}`
}

export function buildReleasePack(candidate: LocalCandidate, version: string): ReleasePack {
  if (!VERSION_PATTERN.test(version)) throw new Error("版本号只能包含字母、数字、点、下划线和连字符。")
  if (!Object.values(candidateGates(candidate)).every(Boolean)) throw new Error("来源、模型评测和人工主审尚未全部通过。")
  if (!candidate.modelEvaluation || !candidate.humanReview) throw new Error("质量复核记录缺失。")

  const referenceFile = `references/skills/${candidate.id.replace(/[^A-Za-z0-9._-]/g, "-")}.md`
  const currentSkills = JSON.parse(repositorySkillData.runtimeFiles["references/skills.json"]) as {
    name: string
    skills: Array<Record<string, unknown>>
  }
  const nextSkill = {
    id: candidate.id,
    name: candidate.name.replace(/（候选）/g, "").trim(),
    account_type: "团队复用写作结构",
    quality_score: candidate.modelEvaluation.score,
    source_count: candidate.sourceCount,
    created_at: candidate.updatedAt,
    hotspot_types: ["结构沉淀", "单源可复核", "人工主审"],
    solves_problems: [candidate.purpose],
    match_signals: [candidate.hook, candidate.progression],
    applicable_scenes: [candidate.purpose],
    research_needs: ["使用前核验当前事实、时间线、公开来源和平台语境。"],
    choose_when: candidate.purpose,
    writing_method: `开头：${candidate.hook}\n推进：${candidate.progression}\n收束：${candidate.ending}`,
    risk_boundary: candidate.riskBoundary,
    reference: referenceFile,
    reference_file: referenceFile,
  }
  const files = { ...repositorySkillData.runtimeFiles }
  files["references/skills.json"] = `${JSON.stringify({
    ...currentSkills,
    version,
    skills: [...currentSkills.skills.filter((skill) => skill.id !== candidate.id), nextSkill],
  }, null, 2)}\n`
  files[referenceFile] = referenceMarkdown(candidate)

  return {
    schema_version: 1,
    version,
    active_skill_count: currentSkills.skills.length + 1,
    candidate: {
      id: candidate.id,
      name: candidate.name,
      sourceCount: candidate.sourceCount,
      qualityScore: candidate.modelEvaluation.score,
      evaluatedAt: candidate.modelEvaluation.evaluatedAt,
    },
    files,
  }
}
