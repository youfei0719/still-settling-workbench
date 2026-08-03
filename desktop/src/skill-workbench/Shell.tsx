import { BookOpen, CheckCircle2, Settings2, Sparkles } from "lucide-react"
import settlingMark from "../assets/settling-mark.svg"
import { useEffect, useRef, type ReactNode } from "react"
import type { WorkbenchPage } from "./types"

const navItems = [
  { page: "deposit" as const, label: "沉淀 Skill", icon: Sparkles, group: "主流程" },
  { page: "library" as const, label: "写作 Skill 库", icon: BookOpen, group: "资产" },
  { page: "diagnostics" as const, label: "系统诊断", icon: Settings2, group: "高级" },
]

export function WorkbenchShell({ page, candidateCount, onPageChange, children }: { page: WorkbenchPage; candidateCount: number; onPageChange: (page: WorkbenchPage) => void; children: ReactNode }) {
  const mainRef = useRef<HTMLElement>(null)

  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0, left: 0 })
  }, [page])

  return <div className="skill-shell">
    <aside className="skill-sidebar" aria-label="依旧沉淀主导航">
      <div className="skill-brand"><span className="brand-mark"><img src={settlingMark} alt="" /></span><div><strong>依旧沉淀</strong><small>短视频写作 Skill 工作台</small></div></div>
      <nav>
        {navItems.map((item, index) => <div className="nav-group" key={item.page}>
          {(index === 0 || navItems[index - 1].group !== item.group) ? <span>{item.group}</span> : null}
          <button type="button" aria-label={item.label} aria-current={page === item.page ? "page" : undefined} title={item.label} className={page === item.page ? "is-active" : ""} onClick={() => onPageChange(item.page)}><item.icon size={15} /><strong>{item.label}</strong>{item.page === "library" && candidateCount ? <em>{candidateCount}</em> : null}</button>
        </div>)}
      </nav>
      <div className="main-path"><span>主路径</span><p>从可验证来源沉淀可复用写法，经过质量复核后交付给团队与 Codex。</p></div>
    </aside>
    <div className="skill-main">
      <header className="asset-header">
        <div><span>Skill 资产主线</span><strong>授权来源 → 真实稿件 → 结构沉淀 → 质量复核 → 正式版本 → 发布与加载</strong></div>
        <div className="header-flow" aria-label="当前流程状态"><span className={page === "deposit" ? "is-current" : ""}>沉淀 Skill</span><span className={page === "library" ? "is-current" : ""}>团队 Skill 库</span><span>Codex 同步</span></div>
        <div className="team-account"><CheckCircle2 size={14} /><strong>内容策略组</strong><small>stable 文件完整性已校验</small></div>
      </header>
      <main ref={mainRef}>{children}</main>
    </div>
  </div>
}
