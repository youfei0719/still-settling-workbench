import type { LocalCandidate } from "./types"
import { candidateGates } from "./workflow"

// The native publisher owns runtime construction. React may only authorize a candidate ID.
export function preparePublishCandidate(candidate: LocalCandidate) {
  if (!Object.values(candidateGates(candidate)).every(Boolean)) {
    throw new Error("来源、模型评测和最终发布确认尚未全部通过。")
  }
  return candidate.id
}
