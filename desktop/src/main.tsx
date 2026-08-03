import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import SkillWorkbench from "./skill-workbench/SkillWorkbench"
import "./index.css"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <SkillWorkbench />
  </StrictMode>,
)
