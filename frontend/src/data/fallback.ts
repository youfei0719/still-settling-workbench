import type { AnalyzeTextResponse, WorkbenchOverview } from "@/types/workbench"

// The public build must not ship source videos, personal Skill assets, or
// historical production data when the local API is unavailable.
export const fallbackOverview: WorkbenchOverview = {
  tasks: {
    processing: 0,
    queued: 0,
    completed: 0,
    failed: 0,
  },
  templates: [],
  recent_analyses: [],
  generated_scripts: [],
}

export const emptyAnalysis: AnalyzeTextResponse | null = null
