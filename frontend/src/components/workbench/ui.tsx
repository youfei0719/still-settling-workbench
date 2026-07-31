import { Card as HeroCard } from "@heroui/react"
import type { ReactNode } from "react"
import type { RiskLevel, TaskStatus } from "@/types/workbench"

export function Card({
  children,
  className = "",
}: {
  children: ReactNode
  className?: string
}) {
  return <HeroCard className={`surface-card ${className}`}>{children}</HeroCard>
}

export function SectionHeader({
  title,
  description,
  action,
}: {
  title: string
  description?: string
  action?: ReactNode
}) {
  return (
    <div className="section-header">
      <div>
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {action}
    </div>
  )
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode
  tone?: "neutral" | "success" | "warning" | "danger" | "accent"
}) {
  return <span className={`status-badge status-badge-${tone}`}>{children}</span>
}

export function StatusBadge({ status }: { status: TaskStatus }) {
  const map: Record<
    TaskStatus,
    {
      label: string
      tone: "neutral" | "success" | "warning" | "danger" | "accent"
    }
  > = {
    pending: { label: "等待中", tone: "neutral" },
    processing: { label: "处理中", tone: "accent" },
    completed: { label: "已完成", tone: "success" },
    needs_upload: { label: "换输入继续", tone: "warning" },
    failed: { label: "失败", tone: "danger" },
    cancelled: { label: "已取消", tone: "neutral" },
  }
  const item = map[status]
  return <Badge tone={item.tone}>{item.label}</Badge>
}

export function RiskBadge({ level }: { level: RiskLevel }) {
  const map: Record<
    RiskLevel,
    { label: string; tone: "success" | "warning" | "danger" }
  > = {
    low: { label: "低风险", tone: "success" },
    medium: { label: "中风险", tone: "warning" },
    high: { label: "高风险", tone: "danger" },
  }
  const item = map[level]
  return <Badge tone={item.tone}>{item.label}</Badge>
}

export function EmptyState({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <div className="state-box">
      <strong>{title}</strong>
      <span>{description}</span>
    </div>
  )
}

export function SkeletonLines() {
  return (
    <div className="skeleton-stack" aria-label="加载中">
      <span />
      <span />
      <span />
    </div>
  )
}
