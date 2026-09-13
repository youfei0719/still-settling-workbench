# UI 组件命名与 UX 选型

参考素材：

- BoardUI：app shell、sidebar navigation、KPI card、data table、status badge、filter bar、analysis dashboard。
- HeroUI：Button、Card、Tabs、Table、Modal、Drawer、Toast、Select、Textarea 等可访问组件语义。
- NameThatUI：先命名组件，再实现组件，避免把 popover、modal、drawer、toast、badge、chip 混用。
- Component Gallery：按页面任务选择组件模式，而不是按装饰效果堆界面。
- ChatCut：把"提示词 -> 脚本 -> 镜头建议 -> 字幕节奏 -> 导出"串成内容生产链路。
- GEORank：采用"诊断 -> 方案 -> 资产沉淀 -> 后台管理"的产品结构。

页面映射以 [product-baseline.md](product-baseline.md) 的信息架构为准：创作主线在前，资产与高级能力在后。

## 页面组件映射

| 页面 | 用户任务 | 组件选型 | 说明 |
| --- | --- | --- | --- |
| 新建稿件 · 选题 | 10 秒内输入选题并开始研究 | textarea、primary button、可选补充字段（折叠） | 第一屏极简；不强制输入类型、时长、账号、语气 |
| 新建稿件 · 研究 | 阅读 ResearchBrief，确认事实范围 | stepper、事实分组（已确认 / 存疑 / 观点）、来源列表 | 明确区分 Verified Fact、Uncertain Claim、Opinion |
| 新建稿件 · 角度 | 从 4–8 个角度中做人工选择 | Angle 卡片单选列表、自定义角度输入、风险提示 | 不使用伪精确评分；先角度后结构 |
| 新建稿件 · 素材 | 勾选允许进入正文的材料 | MaterialCard 列表、来源徽标、checkbox、风险提示 | 用户拥有使用 / 不使用控制权 |
| 新建稿件 · 结构 | 选择推荐结构或通用结构 | 结构卡片、骨架预览、fallback 提示 | 无 Skill 匹配时使用通用写作骨架继续 |
| 生成设置 | 调整账号类型 / 时长 / 语气 / 目标 | select、segmented control、默认值 | 全部有默认值，不修改也能继续 |
| 成稿编辑器 | 编辑完整稿件 | 编辑器、版本列表、字数 / 时长提示、导出按钮 | 正文不允许占位符；材料不足显式标注 |
| 审稿 | 处理 AI 痕迹标注与风险项 | 标注高亮、局部改写浮层、风险清单（Warning / Must Fix / Blocked） | 标注默认不自动整篇重写；选中文字触发局部改写 |
| 导出 | 导出 Markdown / JSON | 导出面板、copy button、download button、toast | 导出前带 FinalRiskReview |
| 结构库 / 参考稿库 | 筛选和复用写作结构、真人参考稿 | filter bar、data table、card row、tag/chip、drawer | 资产区，不是默认首页 |
| Skill 工厂 | 链接解析、转写、结构拆解、评测、发布、Codex Sync | 沿用现有工作区组件 | 高级功能；不阻塞普通写稿 |
| 系统设置 | 配置模型、会话、发布项目 | 表单、status badge、验证按钮 | 凭证、门禁、人审记录默认只在这里出现 |

## 状态规范

所有核心流程必须具备：

- loading：研究中、生成中、改写中、导出中（展示真实阶段，不制造虚假百分比）。
- empty：无研究结果、无角度、无素材、无结构、无参考资料。
- error：研究失败、来源不足、接口不可用、材料不足（可继续前进时必须给出 fallback）。
- success：研究完成、角度已选、素材已确认、成稿生成、风险通过、导出完成。

## 术语规范（用户侧）

| 用户看到 | 不要使用 |
| --- | --- |
| 写作结构 | Skill（除非在 Skill 工厂内） |
| 结构库 / 参考稿库 | 资产主线、Skill 资产主线 |
| 换一种方式继续 | 需上传兜底 |
| 材料不足 | 你来填写 / 待补充 |
| 高级信息 | Gate / Runtime / SHA（直接暴露） |

## 动效边界

- Transitions.dev：只用于页面面板、tabs、结果区的轻量入场和状态切换。
- Border Beam：只用于当前主任务卡或生成按钮附近的小面积强调。
- Animated Buttons：只用于生成、研究、导出这类关键按钮的 hover/loading/success，不给所有按钮加动画。
