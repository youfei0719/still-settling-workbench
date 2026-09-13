# 当前改造路线（创作主线）

本文件承接 [product-baseline.md](product-baseline.md)：记录当前实现与目标产品的差距、Phase-by-Phase 改造计划和进入代码改造前的检查清单。

## 一、目标

把产品从“越来越复杂的 Skill 管理工具”改回“每天能用来写营销号稿件的内容创作工作台”，同时保留现有底层能力与 Skill 资产。

改造原则：

```text
reuse / refactor / move / rename / extend
不是 rewrite everything
```

- 不推倒重写：视频解析、转写、结构分析、局部改写等已经可用的能力继续保留。
- UI 优先服务创作过程：技术状态、Agent log、Gate、Runtime、SHA、GitHub、Codex 长期不暴露在普通用户主界面。
- 不假装进度：真实联网 / LLM 调用展示真实状态，不制造虚假百分比。
- 每完成一个 Phase 都测试，不把六个 Phase 全改完才验证。

## 二、当前实现与目标产品的差距

（基于当前 `douyin-script-web` 工作区真实代码整理）

### 前端

| 组件 | 当前行为 | 目标行为 | 建议处理 |
| --- | --- | --- | --- |
| `AppShell.tsx` | 顶栏写死“Skill 资产主线”；主导航为“写作工作台 / 沉淀 Skill / 审核导出”；资产区为“写作 Skill 库” | 导航体现创作主线：新建稿件、稿件项目、结构库、参考稿库、Skill 工厂、系统设置 | 重构（Phase 1） |
| `App.tsx` | 默认页 `page = "link"`，即先进入“沉淀 Skill” | 默认进入“新建稿件”，10 秒内可输入选题 | 重构（Phase 1） |
| `ContentWorkflow.tsx` | 已实现 6 步：选题 → 素材 → 角度 → Skill → 大纲 → 初稿；研究=用户粘贴文本 + 可选事实核验；无第二轮定向素材研究；无 Material 选择；生成“结构工作稿” | 9 步创作主线：选题 → 研究 → 角度 → 素材（二次定向） → 结构 → 完整成稿 → 审稿 → 导出；无 Skill fallback | 扩展 + 重构（Phase 1–4），保留组件骨架 |
| `HotspotStudio.tsx` | 当前未被任何页面引用（死代码）；旧交互要求先选模板 Skill 再生成 | 不再作为主流程入口 | 删除或降级为 legacy；资产能力不删除 |
| `LinkConsole.tsx` | 当前默认首页与核心入口 | 迁移为 Skill 工厂入口 | 迁移导航，不删除 |
| `AnalysisWorkspace.tsx` | 结构分析结果页，支持沉淀为 Skill | 保留：Skill 工厂 + 参考稿沉淀流程 | 复用 |
| `TemplateLibrary.tsx` | “写作 Skill 库”作为主要资产页 | 拆为“结构库 / 参考稿库”（用户侧“写作结构”），治理信息进 Skill 工厂 | 复用 + 拆职责（Phase 1/3） |
| `ReviewExport.tsx` | 已有选中文字局部改写、改写建议、事实来源、风险项、版本、导出；混入外部门禁、人审模板、凭证入口 | 作为成稿编辑器 + AI 痕迹标注 + 风险审稿 + 导出；门禁 / 人审 / 凭证移入系统诊断 | 复用 + 拆分（Phase 1/4/5） |
| `InitialSetupPanel / CodexSyncPanel / MaterialTaskPanel` | 系统诊断高级页 | 保留为 Skill 工厂 / 系统设置，不阻塞创作 | 保留（Phase 1 调整导航） |

### 后端接口与数据对象

| 对象 / 接口 | 当前行为 | 目标行为 | 建议处理 |
| --- | --- | --- | --- |
| `POST /drafts/prepare` | 研究简报=用户文本 + 可选事实核验；角度为 3 个硬编码模板角度；同时返回 Skill 匹配 | 研究=真实联网研究；角度 4–8 个；角度选定后再做定向素材研究；结构匹配在角度之后 | 重构（Phase 2–3） |
| `POST /drafts/rewrite-tasks` | 生成 3 版“写作结构工作稿”（提示词明确要求“不直接替用户写完整成稿”） | 一次生成完整可编辑 GeneratedScript（无占位符；材料不足时明示） | 重构（Phase 4） |
| `POST /scripts/selection-rewrite` | 已有选中文字局部改写 + targeted research | 复用为 AI 痕迹标注后的局部改写链路 | 复用（Phase 5） |
| 事实核验（`verify_major_claim_structured`） | 已有结构化事实核验与来源 | 复用于研究阶段与素材阶段 | 复用（Phase 2–3） |
| `risk_check` | 单次风险检查（生成后） | 扩展为分阶段：Research / Angle / Material / Draft / FinalRiskReview | 扩展（Phase 2–4） |
| `ResearchBrief` | 已存在：verified_facts / timeline / platform_context / risk_flags / research_gap / sources | 扩展存疑信息、舆论观点、公众情绪、讨论背景 | 扩展（Phase 2） |
| `AngleCandidate` | id / name / thesis / reason / required_facts / risk_notes | 扩展为完整 Angle Card（支撑材料、缺失材料、撞题判断） | 扩展（Phase 2） |
| `GeneratedScript` | 已含 title / spoken_script / shot_suggestions / subtitle_rhythm / comment_cta / risk_check / version | 从“结构工作稿”改为完整可编辑稿；保留 editor / version / export 契约 | 复用契约 + 改生成逻辑（Phase 4） |
| `WritingProject` | 不存在 | 新增聚合根：topic、research、selected_angle、materials、selected_materials、selected_structure、reference_scripts、generation_settings、draft、review_annotations、risk_result、final_script | 新增（Phase 1–3） |
| `MaterialCard / SelectedMaterials` | 不存在 | 第二轮定向研究产物 + 用户确认结果 | 新增（Phase 3） |
| `ReferenceScript` | 不存在 | 真人参考稿资产（manuscript-extractor 与人工保存） | 新增（Phase 6） |
| `ReviewAnnotation` | 不存在（只有风险项） | AI 痕迹标注结果，联动局部改写 | 新增（Phase 5） |
| 持久化 | 已持久化 source video / transcript / analysis / template / generated script；草稿流程为内存态 | WritingProject 与各步骤状态持久化；兼容现有表，先设计再迁移 | 扩展（Phase 1–3） |
| 外部门禁 / 人审 / Codex 发布 | 已实现，且暴露在审核导出页 | 保留能力，移入系统诊断 / Skill 工厂；普通写稿不依赖 | 迁移（Phase 1） |

### 尚未接入

| 能力 | 当前状态 | 计划 |
| --- | --- | --- |
| `human-writing` 中文自然写作规则 | 未接入 | Phase 5：生成阶段生效 |
| `shuorenhua` annotation | 未接入 | Phase 5：审稿阶段默认 annotation，不整篇洗稿 |
| Humanizer-zh | 未在本仓库接入 | 保留为 fallback / legacy，退出默认主链路 |

### 跨仓库冲突（需在 Phase 5 一并处理）

`douyin-writing-skills`（独立发布仓库，Codex 侧运行时）当前存在与新方向冲突的约定：

- 其 `SKILL.md` 加载器第 6 步要求：任何最终中文稿件、标题、文案都必须读取 `humanizer-zh/SKILL.md` 并执行一次“整篇最终清洗”。
- 这与本产品基线“human-writing 在生成阶段生效 + shuorenhua 只做 annotation + 局部改写”的两层方案冲突，也与“不要多套 Humanizer 连续整篇清洗”的约束冲突。

处理原则（本轮不动该仓库，原因：stable 运行时按哈希不可变，加载器契约变更必须与版本发布一起做）：

1. Phase 5 落地本仓库两层方案后，再评估修改 `douyin-writing-skills` 的加载器约定。
2. 修改时必须同步发布新的 stable 运行时或新版本，不能只改源文件。
3. 保留 humanizer-zh 作为可调用的 fallback，不作为默认必经步骤。

## 三、Phase 计划

### Phase 1：信息架构（已实现，等待用户实际体验确认）

只改：

- 默认首页（改为新建稿件）
- 导航（创作主线 + 结构库 / 参考稿库 + Skill 工厂 / 系统设置）
- WritingProject 主流程壳
- Stepper（8 步状态：选题 → 研究 → 角度 → 素材 → 结构 → 成稿 → 审稿 → 导出）
- 页面状态
- 前进 / 后退 / 状态保留
- 一个真实选题可以走完整流程

允许 Mock Data。目标：先验证产品流程，不接新能力。

验收：打开工作台 10 秒内可以输入选题；旧 Skill 工厂入口仍可达；现有发布 / 诊断能力不丢失。

#### Phase 1 执行约束（2026-09-13 确认，必须遵守）

1. **暂不做数据库大改**：不为 WritingProject 新建大量数据库表、Alembic migration、CRUD 和复杂关系。优先复用现有状态和数据对象，必要时使用最小持久化或前端临时状态。真正持久化设计在流程确认可用后逐步落地。
   - Phase 1 成功标准不是“数据库模型完成”，而是：**能顺畅地从一个选题开始，沿新的创作流程向后走。**
2. **HotspotBrief 不破坏式废弃**：不用 ResearchBrief 完全替换 HotspotBrief，不为了重命名做数据库迁移。优先扩展现有 HotspotBrief / ResearchBrief 使其能承载 `summary / timeline / verified_facts / uncertain_claims / opinions / controversies / audience_sentiment / candidate_angles / risk_flags / sources`。UI 层统一称“研究简报 / Research Brief”。原则：**reuse / extend 优先于 rename / replace。**
3. **HotspotStudio 及旧流程组件不删除**：只从主导航移除、从新 WritingProject 主流程断开、标记 legacy。等新流程经真实选题验证后再清理。本轮优先迁移和复用，不做提前清仓。
4. **禁止过度视觉重构**：只解决默认首页、信息架构、主导航、WritingProject 流程壳、Stepper、各阶段基础状态、前进/后退、一个真实选题走通。不投入设计系统重做、大规模 CSS 重构、动画、装饰性交互、复杂卡片视觉、无关响应式细节。允许使用简单甚至临时 UI——先验证工作流，再优化视觉。
5. **Phase 1 完成后暂停**，输出变更报告并等待用户实际体验确认，**不得自动进入 Phase 2**。

#### Phase 1 交付与验证（2026-09-13）

已交付：

- 默认首页「新建稿件」（大输入框 + 可选补充材料 + 开始研究）。
- 8 步 WritingProject 流程壳：选题 → 研究 → 角度 → 素材 → 结构 → 成稿 → 审稿 → 导出，支持前进 / 后退 / 步骤跳转 / 状态保留。
- 导航重排：＋新建稿件 / 稿件项目 —— 结构库 / 参考稿库 —— Skill 工厂 / 系统设置。
- Skill 工厂页保留全部旧能力入口（链接解析、结构分析、Skill 库治理、旧版审核导出）。
- 研究步骤复用现有 `POST /drafts/prepare`；`ResearchBrief` 原位扩展（summary / uncertain_claims / opinions / controversies / audience_sentiment / candidate_angles），无数据库迁移。
- WritingProject 状态只在前端内存保存（App 持有），刷新清空 —— Phase 1 明确不做数据库持久化。

验证：

- 前端构建通过；Playwright 桌面 + 移动端 20 passed / 6 skipped（skip 为历史遗留用例）。
- 后端单元测试 65 passed。
- LLM 离线 smoke 通过；依赖检查 required 2/2、optional 6/6。
- 真实选题（品牌代言人更换）走完全流程并截取 10 张页面截图，见 `frontend/test-results/phase1/`。

#### Phase 1 最小产品定义

默认首页「新建稿件」第一屏只需要：大输入框（你要写什么？）、可选补充材料、主按钮「开始研究」。

进入项目后显示流程：选题 → 研究 → 角度 → 素材 → 结构 → 成稿 → 审稿 → 导出。

每一步至少能够：正确展示当前阶段、前进、后退、保留已经输入或选择的状态。

不真正实现联网研究、结构推荐、完整生成等后续能力，除非复用现有接口几乎没有额外成本。

主导航：＋新建稿件 / 稿件项目 / —— / 结构库 / 参考稿库 / —— / Skill 工厂 / 系统设置。未真正实现的页面用合理 placeholder，但现有能力不能丢失、Skill 工厂必须还能进入旧能力、系统设置必须保留、普通写稿不依赖 Skill / GitHub / Codex 配置。

### Phase 2：研究 + 角度（已实现，等待用户实际体验确认）

复用：Fact Verification、HotspotBrief / ResearchBrief、Sources。

实现：

- Research（联网研究 + 存疑区分 + 来源证据）
- Angle Cards（4–8 个）
- SelectedAngle（角度在结构之前）

验收：输入选题后首先得到研究结果；已确认事实与存疑信息明显区分；角度可人工选择或自定义。

#### Phase 2 交付与验证（2026-09-13）

已交付：

- 新增研究接口 `POST /research/briefs`：联网研究 + 4–8 个角度候选，**不返回任何 Skill / 结构匹配**。
- 联网研究复用 Codex 通道（`allow_web_search=True`），严格区分 Verified Fact / Uncertain Claim / Opinion，来源带 URL / 发布方 / 时间。
- 核验分级：`verified`（≥2 个独立来源且事实由页面直接支持）/ `partial` / `preview`；未达到 verified 时事实一律降级为待核验，UI 显示「事实候选 / 用户提供的信息」与研究预览说明。
- 角度强制决策：取消「暂不设定」，未产生 SelectedAngle 时无法进入素材及后续步骤（确认按钮与 Stepper 双重拦截）。
- 结构匹配解耦：进入结构步骤且已有 SelectedAngle 时才惰性调用 `/drafts/match-skills`；`/drafts/prepare` 标记为 legacy，研究阶段不再耦合结构匹配。
- 新增 `WORKBENCH_CODEX_AUTH_MODE=local_codex`：联网研究可复用本机 Codex 登录态（适用于中转不支持 Responses API 流式返回的环境）。

验证：

- 真实联网研究（本机 Codex 登录态通道，123 秒）：3 个来源（索尼音乐官方页、澎湃新闻 2 篇），4 条来源直接支持的事实，3 条存疑、2 条观点、4 条争议，4 个角度卡片；模型主动指出“口碑两极”缺乏统计证据，未把前提写成事实。
- 离线兜底：`verification_status=preview`，不出现「已确认事实」，输出 6 个明显不同的角度。
- 测试：新增 3 条 Phase 2 研究契约单测；后端 68 项单测通过；Playwright 桌面 + 移动端 20 passed / 6 skipped。


### Phase 3：素材 + 结构（已实现，等待用户实际体验确认）

实现：

- 二次定向研究（面向 SelectedAngle）
- Material Cards + SelectedMaterials（用户勾选）
- Structure recommendation（1–3 个）
- 无 Skill fallback（通用写作骨架）

验收：选定角度后进行第二次定向素材研究；用户可以明确选择哪些 Material 进入正文；没有现成 Skill 时也能继续生成。

#### Phase 3 执行约束（2026-09-13 确认，必须遵守）

1. **逐条事实必须可追溯来源**：`verified_facts` 逐步支持 `id / claim / source_ids[] / confidence / note`；前端必须让用户看清「哪一条事实由哪个来源支持」。`verification_status=verified` 只代表整体核验状态，不代表所有字段都是事实；`uncertain_claims` 与 `opinions` 保持独立语义。本阶段允许兼容现有结构，不做数据库迁移。
2. **Angle 支撑依据必须区分证据类型**：至少区分 verified facts / opinion 或 public sentiment / examples 或 cases / missing evidence。「网友这么认为」不得转写成「事情就是这样」。第二轮研究必须保持同样的事实纪律。
3. **运行配置保护**：未经用户确认，不得主动修改 `.env`、模型、API Base、认证模式、代理、Codex Home 或其他运行环境配置。发现问题先报告：当前配置 / 失败原因 / 拟修改内容 / 影响 / 回退方式。
4. 第二轮研究是 **Angle-driven Research**：query 由 Topic + SelectedAngle + ResearchBrief + 当前缺失证据共同生成，禁止简单重复第一次搜索。
5. `MaterialCard` 至少包含 `id / type / title, summary / content / source / publisher / published_at / source_url / verification_status / relevance_to_angle / suggested_usage / risk / selected`；`type` 至少区分 fact / quote / opinion / case / data / background / comparison；来源或证据不足时明确标注 `uncertain`。
6. 每张卡必须回答「这是什么」和「它为什么对我选的这个角度有用」；建议用途要具体（如「第二段事实背景」），不使用伪精确相关度打分。
7. 用户必须显式选择素材：`SelectedMaterials` 才能进入后续结构推荐与成稿；可提供全选/取消便利操作，但不默认把全部搜索结果塞给模型；未选素材时提示「当前没有选择支撑材料，继续写作可能主要依赖通用推理」，但不强制至少选 N 条。
8. 第二轮研究必须有明确停止条件（核心角度证据足够 / 主要 evidence gap 补齐 / 来源数量合理 / 继续搜索信息增量有限），V1 不追求搜尽全网；优先复用第一次研究已有的来源，避免重复打开相同页面；保持真实状态反馈，不做虚假百分比。
9. 结构推荐必须在 SelectedMaterials 之后：Topic + SelectedAngle + SelectedMaterials → 推荐 1–3 个结构，每个结构解释「结构是什么 / 为什么适合这个角度 / 当前材料如何填进去 / 哪些地方可能材料不足」；用户可选择推荐结构、手动从结构库选择、或使用通用结构。
10. **无 Skill fallback 必须真实可用**：Skill 库为空时仍出现通用写作结构并可继续，不允许出现「请先沉淀 Skill」「无可用 Skill，无法继续」。
11. Phase 3 UI 保持轻量，重点验证：第二轮研究是否真的围绕 Angle、Material Cards 是否有用、用户能否快速选素材、推荐结构是否真正使用 SelectedMaterials。
12. Phase 3 完成后暂停，不进入完整成稿 / human-writing / shuorenhua / Reference Library / WritingProject 持久化。

#### Phase 3 测试要求

至少用 3 个不同类型真实选题（娱乐人物或作品讨论 / 品牌或商业事件 / 泛娱乐社会讨论），每个验证：第一次研究完成、用户选择 Angle、第二轮搜索与第一次明显不同、MaterialCard 可追溯来源、fact 与 opinion 不混淆、用户可选择材料、Structure recommendation 使用 SelectedMaterials、Skill 库为空仍可继续。

#### Phase 3 交付与验证（2026-09-13）

已交付：

- 新增 `POST /research/materials`（Angle-driven 第二轮定向研究）与 `POST /structures/recommend`（基于 SelectedAngle + SelectedMaterials 的结构推荐）。
- 逐条事实可追溯：`ResearchBrief.verified_claims`（`id / claim / source_ids / confidence / verification_status / note`），来源带稳定 `src-N` id；**没有来源支持的事实自动降级为 uncertain**，前端逐条显示"支持来源"chips 并可点击跳转。
- Angle 证据分类型：`AngleEvidenceBundle`（verified_facts / opinions / examples / missing_evidence）；提示词明确禁止把 opinion 写进事实引用。
- `MaterialCard` 完整字段 + 7 种 type；无来源时强制 `uncertain`；每张卡回答"这是什么"和"为什么对这个角度有用"+ 建议用途。
- 用户显式选择素材（使用 / 不使用 + 全选 / 取消），不默认勾选；`SelectedMaterials` 才进入结构推荐。
- 结构推荐解释"为什么适合这个角度 / 素材如何填进结构 / 可能材料不足的地方 / 使用注意"；通用结构始终可用。
- 第二轮研究带停止条件（核心证据足够 / gap 补齐 / 来源 4-8 个 / 信息增量下降），并复用第一轮已打开来源。

验证：

- 三个真实选题端到端（娱乐人物 / 品牌商业 / 泛娱乐社会）：第一次研究均为 `ai + verified`（4-5 个来源、7-8 条带来源事实、6 个角度）；第二轮均产出 7 张素材卡；结构推荐均给出 3 个结构且确实挂载了已选素材。
- 平均耗时：第一次研究 125s、第二轮定向研究 107s、单次全流程约 270s。
- 空 Skill 库实测（隔离副本、0 个结构）：仅返回通用写作骨架，已选素材正常映射，无"请先沉淀 Skill / 无法继续"文案。
- 测试：后端 75 项单测通过（新增 Phase 3 契约测试 7 项）；Playwright 20 passed / 6 skipped。

修复的两个真实缺陷：

1. 已发布 Skill 的 `writing_method` 是一整段说明，原先直接当 skeleton 会渲染成无法阅读的长句 → 新增解析器拆成 4 步可读骨架（5/5 结构解析成功），解析不出时回退原短步骤或通用骨架。
2. 模型返回无法对应的素材 id 时，原实现会把已选素材映射清空 → 改为仅在模型确实挂上真实素材时才替换本地映射。



### Phase 4：完整成稿（已完成，AI 生成已用真实选题实测）

把“结构工作稿”改成“完整 GeneratedScript”。

保留：editor、version、export。

验收：AI 一次生成完整可编辑稿，正文无占位符；材料不足时明确显示“材料不足”。

#### Phase 4 执行约束（2026-09-13 确认，必须遵守）

1. **生成证据边界（最高优先级）**：正文事实性信息只能来自 ①用户明确输入 ②`SelectedMaterials` ③理解事件所必需且已逐条核验的基础 `verified_claims`。禁止使用 `uncertain_claims`、未选择的 MaterialCard、无来源信息、模型自身记忆补充的事件事实、搜索阶段未出现的新事实。缺材料时返回 Material Gap，不得自行补。
2. `GeneratedScript` 在兼容现有字段基础上扩展 `used_material_ids[] / used_claim_ids[] / material_gaps[]`（必要时加 `evidence_map[]`）；技术 ID 不进正文，但系统必须知道事实依据来源。
3. 生成结束后执行一次 **Evidence Check**：正文中的具体事实性陈述必须能映射到 SelectedMaterial 或 allowed verified claim；不能映射的标为 `unsupported_claim`，从初稿删除或降级表达，不得以确定事实保留。本阶段不做新一轮大规模联网搜索。
4. **Material Gap 不进正文**：禁止 `【这里补案例】/【材料不足】/【等待补数据】/【加入网友观点】` 等占位符；正文必须始终完整可读。证据不足时少写或不写该论点，并在正文之外单独返回 Material Gaps（含"处理：初稿没有把该判断写成事实"）。
5. **结构必须真正控制推进**：生成时实际使用 structure steps + material mapping + material gaps；生成后验证结构主要步骤覆盖、是否重复材料、是否无证据强行填满某一步。缺材料时允许结构自然缩短，不允许内容为填模板注水。
6. **默认只生成 1 篇完整主稿**（可附 2–3 个标题候选、最多 2 个开头候选）；不再让用户在多个完整脚本之间选择。
7. 生成设置前移为轻量步骤（账号类型 / 参考时长 / 语气 / 传播目标，全部有默认值，不修改即可生成）；`durationSeconds` 只是参考，不允许为凑字数注水。
8. 正文生成规则：开头直接进入话题；SelectedAngle 是唯一主线；每段有信息推进；SelectedMaterials 真正被使用；不重复解释；不制造空洞总结；不凭空加入人物动机；opinion 不写成 fact；不新增无来源数据；结尾不强制升华；正文无系统提示 / ID / 结构标签 / 占位符。**这是完整、可靠、可编辑，不是去 AI 味（Phase 5）。**
9. 编辑器复用现有能力（现有 textarea 编辑器模式 + `lib/speech.ts` 字数/时长工具），支持编辑正文与标题、保存修改、查看字数 / 预计时长、保留版本、继续下一步；不开发第二套编辑器，不做 Block Editor。
10. 生成后继续调用现有 Draft Risk，覆盖 unsupported factual claim / uncertain claim 被确定化 / 隐私 / 人身攻击 / 恶意引战 / 未成年人 / 高敏内容 / 客户禁用表达，并区分 Warning / Must Fix / Blocked。不实现 Phase 5 的 AI 痕迹审查。
11. Phase 4 不做：human-writing、shuorenhua、Humanizer、Reference Library、作者画像、自动学习用户修改、Fine-tuning、WritingProject DB 持久化、新一轮大规模联网研究、UI 大改、`.env` / 模型切换。

#### Phase 4 测试要求

至少三个不同类型真实选题（娱乐人物或作品 / 品牌或商业 / 泛娱乐社会讨论）跑完 Research → SelectedAngle → SelectedMaterials → SelectedStructure → GeneratedScript，验证：只有一个主稿、完整口播非模板、无占位符、事实性核心陈述可追溯、未使用未选争议 Material、opinion 未变 fact、SelectedAngle 未跑偏、结构步骤被执行、缺材料不编造、Material Gap 在正文之外、editor 可修改、保存版本正常、无 Skill fallback 生成正常。额外增加对抗测试：故意选择一个证据不足的 Angle，验证不为写完整文章而编事实。

#### Phase 4 交付与验证（2026-09-13）

已交付：

- 新增 `POST /scripts/generate`：按 Allowed Evidence 生成**一篇**完整主稿 + 证据追踪 + 证据检查 + Draft Risk。
- Allowed Evidence = 用户输入 + SelectedMaterials + 与已选素材关联的已核验 `verified_claims`；未选素材、`uncertain_claims`、无来源信息与模型记忆一律不得进入正文。
- `GeneratedScript` 扩展：`title_candidates / used_material_ids / used_claim_ids / material_gaps / evidence_map / evidence_check / structure_coverage / evidence_policy`（兼容追加，默认空）。
- Evidence Check 两级：模型复核（删除 / 降级 / 转为观点）+ 确定性兜底检查（按行句切分，含数字或事实动词的陈述必须能在 Allowed Evidence 中对应）；过滤后正文若过短，改用克制的完整短稿，**正文永不为空**。
- Material Gap（缺口 + 处理）只出现在正文之外；正文禁止任何占位符、素材编号与结构标签。
- 结构执行：生成时使用 structure steps + material mapping + structure gaps，并要求返回 `structure_coverage`。
- 成稿步骤提供轻量 Generation Settings（账号类型 / 参考时长 / 语气 / 传播目标，均有默认值）+ textarea 编辑器 + 字数 / 预计时长 + 版本保存与恢复。
- 通道错误对用户只显示一句人话（如“本机 Codex 用量已达上限”），不泄漏底层日志。

验证：

- 后端 84 项单测通过（新增 Phase 4 契约测试 9 项，含证据边界、无来源降级、空正文防护、AI 路径删除无依据事实、虚报 id 过滤、对抗测试）。
- 三个真实选题经真实 HTTP 链路（离线模式）验证：正文非空、无占位符、未使用未选素材、缺口在正文外、风险等级可判定。
- Playwright 20 passed / 6 skipped；前端构建通过。

通道分工（2026-09-13 实测结论）：

- 完整成稿 / 结构推荐 / 证据复核等**不需要联网检索**的调用 → 默认走中转（`WORKBENCH_LLM_TRANSPORT=litellm` + `openai/gemini-3.1-pro-low`）。
- 联网研究（第一轮 / 第二轮）→ 必须走能真正执行 Web 检索的通道：`WORKBENCH_RESEARCH_TRANSPORT=codex_cli` + `WORKBENCH_RESEARCH_CODEX_AUTH_MODE=local_codex`。
- 为什么分开：实测 tokenflux 中转只返回 message、**不产生 `web_search_call`**（模型会凭记忆编造“已联网确认”的结论），因此中转不能用于研究；而本机 Codex 通道有真实检索能力。两者分工后，生成走中转、检索走 Codex。

真实 AI 实测（3 个选题 + 1 个对抗选题）：

| 选题 | 生成 | 正文 | 占位符 | 未选素材泄漏 | 缺口进正文 | 证据检查 | 风险 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 周杰伦《最伟大的作品》口碑两极 | ai / 74s | 550 字 | 无 | 无 | 无 | 已处理 2 条（含编造统计） | medium→low（修正误报后） |
| 某茶饮品牌联名价格争议 | ai / 40s | 351 字 | 无 | 无 | 无 | 通过 | low |
| 反向旅游 / 小众目的地 | ai / 37s | 354 字 | 无 | 无 | 无 | 通过 | low |
| 对抗：证据不足的「老用户大规模流失」 | ai / 57s | 32 字（克制短稿） | 无 | 无 | 无 | 移除 4 条无依据陈述 | low |

平均：生成约 50-65s，全流程（含两轮联网研究）约 300s。




### Phase 5：去 AI 味

接入：

- human-writing（生成阶段）
- shuorenhua annotation（审稿阶段）
- 现有 selection rewrite（局部改写）

验收：AI 痕迹可被标注并直接触发现有局部改写；不出现多套 Humanizer 连续整篇清洗。

### Phase 6：Reference Library

复用：真实稿件、manuscript-extractor 产物。

实现简单 Reference 检索（2–4 篇 few-shot）。不做复杂 Style Learning、作者画像、Fine-tuning。

验收：结构与 ReferenceScript 相互独立；Reference 只影响推进、节奏、开头转折结尾，不复制事实与句子。

## 四、进入代码改造前的检查清单

Markdown 修改完成以后，按顺序确认：

1. 重新阅读修改后的文档。
2. 当前产品只有一套主流程（product-baseline.md 第 3–5 节）。
3. 没有旧 README 或旧架构文档仍然把 Skill 发布描述为主产品。
4. 实施计划和技术边界不冲突。
5. 现有数据尽量兼容（先设计兼容方案，不急着迁移数据库）。
6. 不会删除仍有价值的 Skill 资产。
7. 普通写稿不依赖 GitHub / Codex / Skill 发布配置。

全部通过后，才进入 Phase 1 代码改造。

## 五、历史：v1 执行边界（归档）

以下为 v1 阶段（2026-07 / 2026-08）的执行边界与已完成状态，仅作历史追溯，不再代表当前产品方向：

```text
链接、视频或文本输入
-> 可分析文本
-> 结构分析
-> 模板沉淀
-> 热点反推脚本
-> 风控
-> Markdown/JSON 导出
```

v1 主导航为五页：链接分析台、分析工作区、模板资产库、热点反推室、审核导出。

v1 已完成的能力（继续保留，作为当前版本的底层）：

- 文本闭环：纯文本、字幕、转写文本可进入分析、模板、热点生成、风控和导出。
- 视频闭环：中文口播和硬字幕样例已验证上传、FFmpeg、FunASR、PaddleOCR、统一文本、结构分析、脚本生成和临时媒体清理。
- 模型稳定性：ASR/OCR 在独立 `.venv-model` 工作进程执行。
- 链接兜底：`douyin-downloader` 已接入；失败时转为视频、字幕或纯文本输入。
- 输出约束：LiteLLM + Instructor/Pydantic；离线模式不伪装为真实模型输出。
- 数据边界：原始视频、音频和 OCR 帧在统一文本成功后自动清理。
- PostgreSQL / Docker：迁移、读写和 API 重启持久化验证完成。
- UI 回归：桌面与移动端 Playwright 工作台测试通过。
- 外部门禁：真实链接、真实 LLM、人审质量三项门禁状态和模板生成已实现（迁移后保留在系统诊断）。
