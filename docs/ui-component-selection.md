# UI 组件命名与 UX 选型

参考素材：

- BoardUI：app shell、sidebar navigation、KPI card、data table、status badge、filter bar、analysis dashboard。
- HeroUI：Button、Card、Tabs、Table、Modal、Drawer、Toast、Select、Textarea 等可访问组件语义。
- NameThatUI：先命名组件，再实现组件，避免把 popover、modal、drawer、toast、badge、chip 混用。
- Component Gallery：按页面任务选择组件模式，而不是按装饰效果堆界面。
- ChatCut：把“提示词 -> 脚本 -> 镜头建议 -> 字幕节奏 -> 导出”串成内容生产链路。
- GEORank：采用“诊断 -> 方案 -> 资产沉淀 -> 后台管理”的产品结构。

## 页面组件映射

| 页面 | 用户任务 | 组件选型 | 说明 |
| --- | --- | --- | --- |
| 链接分析台 | 创建分析任务，处理链接失败兜底 | app shell、input group、upload dropzone、progress stepper、status badge、toast | 高优先级入口；移动端保留文本提交 |
| 分析工作区 | 查看结构分析、风险、模板建议 | tabs、data table、analysis panel、empty state、skeleton、error alert | 参考 BoardUI 的表格和状态标签 |
| 模板资产库 | 筛选和复用脚本模板 | filter bar、data table、card row、tag/chip、drawer | 不做卡片墙，以列表和筛选为主 |
| 热点反推室 | 从热点生成多角度脚本 | textarea、select、segmented control、result panel、loading state | 参考 ChatCut 的提示词驱动流程 |
| 审核导出 | 风控检查、复制、导出 | risk checklist、modal dialog、copy button、download button、toast | 导出前必须显示风险状态 |

## 状态规范

所有核心流程必须具备：

- loading：解析中、分析中、生成中。
- empty：无分析结果、无模板、无导出内容。
- error：链接解析失败、文本不足、接口不可用。
- success：分析完成、模板已沉淀、风控通过、导出完成。

## 动效边界

- Transitions.dev：只用于页面面板、tabs、结果区的轻量入场和状态切换。
- Border Beam：只用于当前主任务卡或生成按钮附近的小面积强调。
- Animated Buttons：只用于生成、分析、导出这类关键按钮的 hover/loading/success，不给所有按钮加动画。
