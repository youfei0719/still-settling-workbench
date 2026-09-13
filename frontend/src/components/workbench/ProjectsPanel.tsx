import { ArrowRight, Plus } from "lucide-react"
import { writingProjectStepLabel } from "@/lib/writingProject"
import type { WritingProjectState } from "@/types/workbench"
import { Card, EmptyState, SectionHeader } from "./ui"

/**
 * 稿件项目：列出当前会话创建的 WritingProject（Phase 1 仅前端内存）。
 */
export function ProjectsPanel({
  projects,
  onOpenProject,
  onNewProject,
}: {
  projects: WritingProjectState[]
  onOpenProject: (projectId: string) => void
  onNewProject: () => void
}) {
  return (
    <div className="page-grid">
      <Card className="writing-panel">
        <SectionHeader
          title="稿件项目"
          description="每一篇稿件对应一个 WritingProject；点击可以回到对应步骤继续。Phase 1 只保留在当前会话中，刷新页面会清空。"
          action={
            <button type="button" className="primary-button" onClick={onNewProject}>
              <Plus size={15} />
              新建稿件
            </button>
          }
        />
        {projects.length ? (
          <div className="workflow-choice-list">
            {projects.map((project) => (
              <button
                type="button"
                key={project.id}
                className="workflow-choice"
                onClick={() => onOpenProject(project.id)}
              >
                <span className="workflow-choice-check">
                  <ArrowRight size={14} />
                </span>
                <span>
                  <strong>{project.topic}</strong>
                  <em>
                    当前步骤：{writingProjectStepLabel(project.step)}
                    {project.researchStatus === "done" ? " · 已有研究简报" : ""}
                    {project.draftText.trim() ? " · 已有成稿" : ""}
                  </em>
                  <small>
                    更新于 {new Date(project.updatedAt).toLocaleString()}
                  </small>
                </span>
              </button>
            ))}
          </div>
        ) : (
          <EmptyState
            title="还没有稿件项目"
            description="回到「新建稿件」写下今天要写的选题，项目会自动出现在这里。"
          />
        )}
      </Card>
    </div>
  )
}
