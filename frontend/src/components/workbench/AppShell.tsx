import { Archive, ClipboardCheck, Link2, Settings2 } from "lucide-react"
import type { ReactNode } from "react"

export type PageKey = "link" | "analysis" | "templates" | "diagnostics"

const navItems: Array<{ key: PageKey; label: string; icon: ReactNode }> = [
  { key: "link", label: "沉淀 Skill", icon: <Link2 size={18} /> },
]

const assetItems: Array<{ key: PageKey; label: string; icon: ReactNode }> = [
  { key: "templates", label: "写作 Skill 库", icon: <Archive size={17} /> },
]

const advancedItems: Array<{ key: PageKey; label: string; icon: ReactNode }> = [
  { key: "diagnostics", label: "系统诊断", icon: <Settings2 size={17} /> },
]

function isNavItemActive(activePage: PageKey, itemKey: PageKey) {
  if (itemKey === "link")
    return activePage === "link" || activePage === "analysis"
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
            src="/assets/images/still-settling-mark.svg"
            alt="依旧沉淀"
          />
          <div>
            <strong>依旧沉淀</strong>
            <span>短视频写作 Skill 工作台</span>
          </div>
        </div>

        <nav className="nav-list" aria-label="主流程导航">
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
                className={`nav-item nav-item-secondary ${activePage === item.key ? "nav-item-active" : ""}`}
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
                className={`nav-item nav-item-secondary ${activePage === item.key ? "nav-item-active" : ""}`}
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
            从可验证来源沉淀可复用写法，经过质量复核后交付给团队与 Codex。
          </strong>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            <p>Skill 资产主线</p>
            <strong>
              {"授权来源 -> 真实稿件 -> 结构沉淀 -> 质量复核 -> 正式版本 -> 发布与加载"}
            </strong>
          </div>
          <div className="task-strip" aria-label="当前流程状态">
            <span
              className={`task-pill ${activePage === "link" || activePage === "analysis" ? "task-done" : ""}`}
            >
              沉淀 Skill
            </span>
            <span
              className={`task-pill ${activePage === "templates" ? "task-done" : ""}`}
            >
              团队 Skill 库
            </span>
            <span className="task-pill">Codex 同步</span>
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
