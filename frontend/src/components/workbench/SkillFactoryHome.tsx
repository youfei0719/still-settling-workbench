import { Archive, FileCheck2, Link2, Search } from "lucide-react"
import type { ReactNode } from "react"
import type { PageKey } from "./AppShell"
import { Card, SectionHeader } from "./ui"

/**
 * Skill 工厂：能力沉淀闭环的入口（Phase 1 信息架构）。
 * 保留现有全部旧能力入口（链接解析 / 结构分析 / Skill 库 / 审核导出），
 * 但它们不再出现在普通写稿主流程里。
 */
export function SkillFactoryHome({
  onNavigate,
}: {
  onNavigate: (page: PageKey) => void
}) {
  const entries: Array<{
    page: PageKey
    title: string
    description: string
    icon: ReactNode
  }> = [
    {
      page: "link",
      title: "链接解析与来源沉淀",
      description:
        "从抖音链接、视频、字幕或文本提取真实稿件，作为结构沉淀的授权来源。",
      icon: <Link2 size={16} />,
    },
    {
      page: "analysis",
      title: "结构分析工作区",
      description: "查看钩子、冲突、结构、情绪和结尾拆解，并沉淀为候选结构资产。",
      icon: <Search size={16} />,
    },
    {
      page: "templates",
      title: "Skill 库（治理 / 评测 / 发布）",
      description: "管理候选与正式 Skill：补充来源、发布评测、主审和 Codex 同步。",
      icon: <Archive size={16} />,
    },
    {
      page: "review",
      title: "旧版审核导出（legacy）",
      description: "v1 流程的审核导出工作区。新写稿请走「新建稿件」主流程。",
      icon: <FileCheck2 size={16} />,
    },
  ]

  return (
    <div className="page-grid">
      <Card className="writing-panel">
        <SectionHeader
          title="Skill 工厂"
          description="能力沉淀闭环：优秀视频 / 真人稿件 → 提取转写 → 结构分析 → 人工判断 → 结构资产 / 参考稿 → 必要时发布 Codex Skill。它是创作主线的供血方，不阻塞普通写稿。"
        />
        <div className="workflow-choice-list">
          {entries.map((entry) => (
            <button
              type="button"
              key={entry.page}
              className="workflow-choice"
              onClick={() => onNavigate(entry.page)}
            >
              <span className="workflow-choice-check">{entry.icon}</span>
              <span>
                <strong>{entry.title}</strong>
                <em>{entry.description}</em>
              </span>
            </button>
          ))}
        </div>
      </Card>
    </div>
  )
}
