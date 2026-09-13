import {
  Archive,
  ClipboardCheck,
  FileText,
  FolderOpen,
  Link2,
  Plus,
  Settings2,
} from "lucide-react"
import type { ReactNode } from "react"

/**
 * Phase 1 信息架构。
 *
 * 创作主线（默认首页）在前：
 *   新建稿件 → 稿件项目
 * 资产与高级能力在后：
 *   结构库 / 参考稿库 → Skill 工厂 / 系统设置
 *
 * legacy 页面（link / analysis / templates / review）保留全部旧能力，
 * 只通过「Skill 工厂」进入，不再出现在普通写稿导航里。
 */
export type PageKey =
  | "create"
  | "projects"
  | "structures"
  | "references"
  | "factory"
  | "settings"
  | "link"
  | "analysis"
  | "templates"
  | "review"

const navItems: Array<{ key: PageKey; label: string; icon: ReactNode }> = [
  { key: "create", label: "＋ 新建稿件", icon: <Plus size={18} /> },
  { key: "projects", label: "稿件项目", icon: <FolderOpen size={18} /> },
]

const assetItems: Array<{ key: PageKey; label: string; icon: ReactNode }> = [
  { key: "structures", label: "结构库", icon: <Archive size={17} /> },
  { key: "references", label: "参考稿库", icon: <FileText size={17} /> },
]

const advancedItems: Array<{ key: PageKey; label: string; icon: ReactNode }> = [
  { key: "factory", label: "Skill 工厂", icon: <Link2 size={17} /> },
  { key: "settings", label: "系统设置", icon: <Settings2 size={17} /> },
]

const factoryChildPages: PageKey[] = ["link", "analysis", "templates", "review"]

function isNavItemActive(activePage: PageKey, itemKey: PageKey) {
  if (itemKey === "factory") {
    return (
      activePage === "factory" || factoryChildPages.includes(activePage)
    )
  }
  return activePage === itemKey
}

export function AppShell({
  activePage,
  onNavigate,
  children,
}: {
  activePage: PageKey
  onNavigate: (page: PageKey) => void
  children: ReactNode
}) {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <div className="brand-lockup">
          <img
            className="brand-mark"
            src={`${import.meta.env.BASE_URL}assets/images/still-settling-mark.svg`}
            alt="依旧沉淀"
          />
          <div>
            <strong>依旧沉淀</strong>
            <span>营销内容创作工作台</span>
          </div>
        </div>

        <nav className="nav-list" aria-label="创作主线导航">
          {navItems.map((item) => (
            <button
              type="button"
              key={item.key}
              className={`nav-item ${isNavItemActive(activePage, item.key) ? "nav-item-active" : ""}`}
              onClick={() => onNavigate(item.key)}
            >
              {item.icon}
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="advanced-nav-block">
          <span>资产</span>
          <nav className="nav-list nav-list-compact" aria-label="资产功能导航">
            {assetItems.map((item) => (
              <button
                type="button"
                key={item.key}
                className={`nav-item nav-item-secondary ${isNavItemActive(activePage, item.key) ? "nav-item-active" : ""}`}
                onClick={() => onNavigate(item.key)}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="advanced-nav-block">
          <span>高级</span>
          <nav className="nav-list nav-list-compact" aria-label="高级功能导航">
            {advancedItems.map((item) => (
              <button
                type="button"
                key={item.key}
                className={`nav-item nav-item-secondary ${isNavItemActive(activePage, item.key) ? "nav-item-active" : ""}`}
                onClick={() => onNavigate(item.key)}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="sidebar-footer">
          <span>主路径</span>
          <strong>
            从一个选题走到完整成稿；优秀稿件再反向沉淀为结构与参考稿。
          </strong>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            <p>创作主线</p>
            <strong>选题 → 研究 → 角度 → 素材 → 结构 → 成稿 → 审稿 → 导出</strong>
          </div>
          <div className="task-strip" aria-label="当前流程状态">
            <span
              className={`task-pill ${activePage === "create" ? "task-done" : ""}`}
            >
              新建稿件
            </span>
            <span
              className={`task-pill ${activePage === "projects" ? "task-done" : ""}`}
            >
              稿件项目
            </span>
            <span
              className={`task-pill ${isNavItemActive(activePage, "factory") ? "task-done" : ""}`}
            >
              Skill 工厂
            </span>
          </div>
          <div className="team-chip">
            <ClipboardCheck size={16} />
            内容策略组
          </div>
        </header>
        <main className="main-workspace">{children}</main>
      </div>
    </div>
  )
}
