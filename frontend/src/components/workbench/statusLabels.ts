import type { TaskStatus, VideoExtractionTask } from "@/types/workbench"

type ExtractorStatus = "completed" | "skipped" | "failed"
type ParserStatus = "completed" | "skipped" | "failed"

export function videoTaskStatusLabel(status: VideoExtractionTask["status"]) {
  const labels: Record<VideoExtractionTask["status"], string> = {
    queued: "排队",
    processing: "处理中",
    completed: "完成",
    failed: "失败",
    cancelled: "取消",
  }
  return labels[status]
}

export function videoTaskStatusToBadgeStatus(
  status: VideoExtractionTask["status"],
): TaskStatus {
  if (status === "queued" || status === "processing") return "processing"
  if (status === "completed") return "completed"
  if (status === "failed") return "failed"
  return "cancelled"
}

export function extractorStatusLabel(status: ExtractorStatus) {
  const labels: Record<ExtractorStatus, string> = {
    completed: "已完成",
    skipped: "已跳过",
    failed: "失败",
  }
  return labels[status]
}

export function parserStatusLabel(status: ParserStatus) {
  const labels: Record<ParserStatus, string> = {
    completed: "解析成功",
    skipped: "进入兜底",
    failed: "解析失败",
  }
  return labels[status]
}

export function parserStatusToBadgeStatus(status: ParserStatus): TaskStatus {
  if (status === "completed") return "completed"
  if (status === "failed") return "failed"
  return "needs_upload"
}

export function formatTaskTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))
}
