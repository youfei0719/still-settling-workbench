# 依旧沉淀 · 当前产品基线

状态：**当前产品事实来源（Current Product Baseline）**  
版本：2026-09 产品方向整改（V2 方向）  
适用项目：`douyin-script-web`（远程仓库 `still-settling-workbench`）  
历史基线：《抖音热点脚本网站v1产品方案蓝图》《抖音热点脚本网站技术边界约束》（仅作历史保留，见文末文档地图）

## 0. 使用约束（给人，也给 Agent）

1. 本仓库只允许存在一套“当前产品主流程”，即本文档第 3–5 节。
2. 任何文档、注释、测试、UI 文案提到 v1 流程时，必须明确标注“历史 v1”，不得把 v1 的“链接分析台 → 热点反推室 → Skill 发布”当作当前主流程。
3. 改造顺序固定为：**产品文档 → 验收标准 → 代码**。不允许先改代码再让文档追认。
4. 本轮整改不是推翻重做：现有底层能力、数据模型和 Skill 资产继续保留，调整的是产品主次和创作流程。

## 1. 产品是什么

依旧沉淀是一个面向内部使用的**营销内容创作工作台**。

当前主要服务：

- 抖音
- 娱乐内容、泛娱乐内容
- 营销号
- 短视频口播 / 解说稿

产品核心不是“管理 Skill”，而是：

> 把一个已经由用户确定的选题，从研究、角度判断、素材筛选、写作结构，到完整成稿和风险审查，变成稳定可重复的内容生产工作流。

用户拥有最终：选题权、角度选择权、素材选择权、结构选择权、最终修改权。AI 不替用户决定最终要写什么。

AI 提效的边界是：研究、整理、素材筛选、结构建议、起草、审稿标注、局部改写。AI 不替用户拍板。

### 它不是什么

| 不是 | 原因 |
| --- | --- |
| 不是 Skill 管理工具 | Skill / 结构资产是辅助能力，不是高频使用场景 |
| 不是热点雷达 / 选题推荐系统 | 未来可以有热点推荐 / 灵感池，但 AI 推荐热点不是当前核心流程的前置条件 |
| 不是自动发布 / 冲榜执行系统 | 发布、冲榜、数据回收属于业务运营动作，不进入本轮产品 |
| 不是公网 SaaS | 本机 / 内网使用，不做多租户 |
| 不是“AI 一键出稿取代人” | 用户保留选题、角度、素材、结构的最终决定权 |

## 2. 谁每天会用它

| 角色 | 高频动线 | 频率 |
| --- | --- | --- |
| 内容策划 / 文案（主要用户） | 新建稿件 → 输入选题 → 确认研究 → 选角度 → 选素材 → 选结构 → 拿完整初稿 → 改稿 → 导出 | 每天多次 |
| 编导 / 运营 | 拿导出稿做口播、剪辑、发布准备 | 每天 |
| 内容主审 | 审核结构资产、决定是否进入 Skill 工厂发布流程 | 低频 |

产品优化的第一优先级是“内容策划能不能每天拿它写稿”，而不是“资产管路是否完整”。

## 3. 两个独立但互相供血的闭环

### A. 日常创作闭环（默认首页，约 80% 使用频率）

```text
新建稿件
↓
选题
↓
研究
↓
角度
↓
素材
↓
结构
↓
（生成设置）
↓
完整成稿
↓
审稿（AI 痕迹审查 + 风险审核）
↓
导出
```

每一篇稿件对应一个 `WritingProject`，每一步状态持久化，可以前后返回修改。不允许用“一个 Agent 请求一次自动做完全部流程”替代流程本身。

### B. 能力沉淀闭环（Skill 工厂，辅助资产）

```text
优秀视频 / 真人稿件
↓
链接 / 视频 / 字幕 / 文本
↓
提取 / 转写
↓
结构分析
↓
人工判断
↓
沉淀为结构资产 / 参考稿
↓
必要时发布 Codex Skill
```

现有能力全部保留：视频解析、ASR、OCR、LinkConsole、AnalysisWorkspace、Template / Skill 评测、GitHub 发布、Codex Sync、Stable Runtime。

但这套能力移动到 **Skill 工厂 / 能力资产 / 高级功能**，作为 A 闭环的供血方存在，**不能再阻塞普通写稿**。

## 4. 信息架构与导航

建议的信息架构（实现可微调，但主次关系不允许反转）：

```text
＋ 新建稿件

稿件项目

────────

结构库
参考稿库

────────

Skill 工厂
系统设置
```

- 默认进入：**新建稿件**。不允许默认进入“沉淀 Skill”。
- 普通创作界面不长期暴露：Gate、Runtime、SHA、GitHub、Codex、Agent log、模型配置。这些属于后台资产能力，进入高级信息。
- “删除或弱化全局 Skill 资产主线”：不要让用户打开产品第一眼看到“发布、门禁、GitHub、Codex 同步”。

## 5. 创作流程逐步定义

### Step 1 选题

第一屏必须极简。主要输入：

- **你要写什么？**（大文本框）

可选补充：

- 已有事实
- 链接
- 截图对应文字
- 客户要求
- 禁用表达
- 自己已有观点

主要按钮：**开始研究**。

这一页不强制用户填写：输入类型、视频时长、账号类型、语气、Writing Skill、传播目标。这些不是开始创作前必须解决的问题。

### Step 2 研究

第一次联网研究的目标不是写稿，而是**把这个选题研究清楚**。优先复用并扩展现有 `ResearchBrief`（由 `HotspotBrief` 演进）。

至少包含：

```text
事件摘要
时间线
已确认事实
存疑 / 未确认信息
主要争议
不同舆论观点
公众情绪
当前互联网讨论背景
内容风险 / 事实风险 / 人物风险 / 舆论风险
来源
```

必须区分：Verified Fact、Uncertain Claim、Opinion。不能把网友说法和媒体猜测直接写成事实。保留来源 URL / 发布方 / 时间等证据。

研究完成以后**不直接生成脚本**，进入角度选择。

### Step 3 角度

这是整个系统最重要的人工作决策节点之一。

根据 Topic + Research Brief + 已确认事实 + 舆论观点，生成 4–8 个明显不同的内容角度。

每个 Angle Card 至少包含：

```text
一句话核心观点
为什么这个角度成立
当前有什么材料可以支撑
还缺什么材料
与现有常见内容是否撞题
主要风险
```

不要使用大量伪精确评分（8.7 / 9.2 / 8.4），除非评分真的有稳定依据。更重要的是让用户能判断“这个角度到底讲什么”。

用户选择一个 `SelectedAngle`。

**硬性规则：角度选择必须发生在结构 / Skill 匹配之前。** 当前实现中任何“先匹配 Skill → 再生成方向”的路径都要整改。

### Step 4 素材

用户选定角度以后，执行**第二轮联网研究**：

- 第一轮研究：理解事件。
- 第二轮研究：寻找能够支撑 SelectedAngle 的具体材料。

搜索目标包括：核实事实、时间线细节、公开原始材料、人物案例、旧闻、对比案例、历史评价、当前评价、代表性网友观点、数据、公开采访、可作为开头 / 论据 / 转折的具体内容。

生成 `MaterialCard`，每张至少包含：

```text
内容摘要
来源
发布时间
可信度 / 来源等级
可用于什么位置
风险提示
```

用户拥有“使用 / 不使用”的控制权。只有 `SelectedMaterials` 才能进入最终正文上下文。不允许模型背地里使用用户没有确认的争议性材料。

### Step 5 结构

这个阶段才接入现有 `douyin-writing-skills` 结构资产。用户侧统一把这项能力称为：

**写作结构**

而不是把结构、文风、作者风格全部叫 Skill。

系统根据 Topic + SelectedAngle + SelectedMaterials 推荐 1–3 个结构。每个结构显示：

```text
结构名称
推进骨架
为什么适合当前稿件
主要优势
潜在风险
```

用户可以：选择推荐结构 / 手动从结构库选择 / 使用通用结构。

必须取消 **“没有 Skill 就不能生成”**。正确 fallback：

```text
匹配到结构  → 使用已有结构
没有匹配结构 → 使用通用写作骨架 → 继续生成
```

Skill 是增强项，不是许可证。

### Step 5.5 生成设置（后移、轻量）

保留原有业务字段，但移动到“结构 → 成稿”之间，作为轻量 `GenerationSettings`：

```text
账号类型：娱乐吃瓜号
参考时长：60 秒
语气：真人口语
传播目标：讨论

高级设置 >
```

所有字段有默认值，不修改也能继续。

### Step 6 完整成稿

当前实现中“AI 生成文本结构工作稿 → 用户填写正文”的路径必须取消。

根据原始产品定义，`GeneratedScript` 应该是**完整可编辑稿件**。生成上下文：

```text
Topic
+ Research
+ SelectedAngle
+ SelectedMaterials
+ SelectedStructure
+ ReferenceScripts
+ GenerationSettings
+ Writing Rules
```

一次生成完整内容：

```text
标题
完整口播正文
必要的分镜建议
字幕节奏
评论 / 结尾建议
风险提示
```

正文禁止出现占位符：

```text
【这里补案例】
【添加观点】
【填写数据】
【你来完成】
```

如果某个论据确实缺失，明确显示**材料不足**，而不是把工作重新扔回给用户。

生成阶段必须应用“自然写作规则”（见第 7 节），从源头减少模型腔，而不是写完再洗。

### Step 7 审稿

审稿包含两层，顺序固定：

**第一层：AI 痕迹审查（annotation，不改写）**

默认只标注，不自动整篇重写。标记对象：

```text
模板式转折
空洞总结
重复解释
过度承接
机械排比
报告腔
翻案句
无来源升华
语气过于标准
明显模型套话
```

标注结果落到 `ReviewAnnotation`，用户可直接**选中文字 → 局部改写**（复用已有 Selection Rewrite 能力）。

**第二层：风险审核**

见第 8 节，分阶段执行，最后汇成 `FinalRiskReview`。

### Step 8 导出

导出 Markdown / JSON。导出前必须带 `FinalRiskReview`。导出内容与编辑器内容一致，不允许出现“结构建议”“写作建议”“你来填写”之类的内部提示文本。

## 6. Skill / 资产在产品中的角色

### 6.1 两种资产必须分离

| 资产 | 解决什么 | 来源 | 落地对象 |
| --- | --- | --- | --- |
| StructurePattern（写作结构） | 怎么组织内容 | 结构分析 + 人工判断沉淀 | 现有 `TemplatePattern` |
| ReferenceScript（参考稿） | 真人怎么表达 | manuscript-extractor、已确认优秀视频稿件、用户手动保存的优秀稿件 | 新增 `ReferenceScript` |

结构示例：结果钩子、反差递进、多案例递进、归因结构、人物情绪结构。

### 6.2 ReferenceScript 使用规则（V1 不做复杂 Style Engine）

系统根据 Topic + SelectedAngle + SelectedStructure 检索 2–4 篇相关真人参考稿，仅用于 few-shot。

明确规则：

- 只能学习：信息推进、句子节奏、叙述习惯、开头方式、转折方式、结尾方式。
- 禁止复制：原稿事实、原稿句子、独特表达、原稿观点。

不做：作者画像、AI 词库、长期自动学习用户修改、Fine-tuning。

### 6.3 Codex Skill 的角色

`douyin-writing-skills`（Codex Skill runtime）是结构资产经过治理后的**发布形态**：

```text
结构资产（工作台内） → Skill 工厂治理（来源证据 / 评测 / 主审） → 发布 Codex Skill
```

发布永远由人手动触发，发布门禁只约束“进入 Codex 的分发版本”，不约束普通写稿。

## 7. 中文去 AI 味方案

默认写作方案为两层，不再开发其他花式方案。

### 第一层：生成阶段（接入或借鉴 `KKKKhazix/human-writing`）

目标不是“写完再洗 AI 味”，而是**一开始就减少模型腔**。重点吸收：

- 材料驱动
- 每段必须产生信息推进
- 减少抽象总结
- 避免机械翻案
- 避免报告腔
- 避免强行升华
- 中文口语自然度
- 允许合理的不规则节奏

不要构建新的个人写作规则库。

### 第二层：审稿阶段（接入或借鉴 `MrGeDiao/shuorenhua`）

优先使用 **annotation / diagnosis 模式**，默认不要自动整篇重写。最终链路：

```text
human-writing
↓
完整初稿
↓
shuorenhua annotation
↓
标出 AI 痕迹
↓
局部 rewrite（复用已有能力）
↓
最终人工修改
```

现有 Humanizer-zh：保留为 fallback / legacy 能力，退出默认主链路。不要多套 Humanizer 连续整篇清洗。

## 8. 风险审查（分阶段）

同一套风险规则在不同阶段调用，风险能力不能只在最后出现。

| 阶段 | 检查内容 |
| --- | --- |
| Research Risk | 信息是否可靠、是否谣言、是否缺乏来源 |
| Angle Risk | 是否恶意引战、是否无证据推测人物动机、是否容易构成不当攻击 |
| Material Risk | 来源可信度、隐私、版权 / 肖像、敏感信息 |
| Draft Risk | 事实错误、人身攻击、低俗擦边、未成年人、高敏政治社会内容、平台风险、客户禁用表达 |
| FinalRiskReview | 汇总结论，供导出前确认 |

风险结论分三档：Warning / Must Fix / Blocked。**不允许用风险评分阻断所有流程**，只有 Blocked 才真正阻断导出。

## 9. V1 / V2 边界

### 历史 v1（保留，供追溯，不再作为当前主流程）

- 五页信息架构：链接分析台 / 分析工作区 / 模板资产库 / 热点反推室 / 审核导出
- 主链路：链接输入 → 提取 → 结构分析 → 模板沉淀 → 热点反推 → 风控 → 导出
- 生成形态：写作结构工作稿（用户填空）
- Skill 发布是主叙事

### 当前版本（V2 方向，本文档描述的主流程）

- 创作主线 + Skill 工厂的双闭环
- 完整成稿（无占位符）
- 角度选择发生在结构匹配之前
- 素材二次定向研究 + 用户确认
- 结构资产与参考稿分离

### 明确暂时不做

热点自动预测、完整热点雷达、自动替用户决定选题、账号资产中心、发布排期、数据回收、客户项目管理、冲榜 SOP 工作台、UID 系统、自动学习用户修改习惯、个人 AI 黑词库、Fine-tuning、复杂作者画像、多 Agent 可视化编排、Qdrant 强依赖、Langfuse 大型运营后台。

不要因为技术上可以做，就让这些进入本轮。

## 10. 技术边界（继续遵守原始约束）

保留当前已经工作的技术栈，不趁这次整改过度重构：

- FastAPI
- React
- PostgreSQL
- JSONB
- Pydantic
- Docker / 本地部署
- 现有 LLM 接入层（LiteLLM + Instructor）

当前阶段仍然：

- 不做自训练模型
- 不做 Fine-tuning
- 不做复杂向量数据库强依赖
- 不做多租户 SaaS
- 不做自动发布抖音
- 不做冲榜执行闭环
- 不做数据回收
- 不做大型 Agent orchestration UI

如果 Reference Library 当前数据规模较小：优先使用 PostgreSQL / JSONB + 简单检索，不要为了“AI”引入不必要复杂度。

## 11. 数据对象方向

不改数据库迁移方案，先设计兼容路径。字段名可结合现有数据库重新设计，不要求机械照抄。

### 继续使用（不动）

`SourceVideo`、`Transcript`、`ScriptAnalysis`、`RiskCheck / RiskItem`、`FactSource`、`SkillSourceRecord`、`SkillEvidence`、`SkillEvaluationSummary`、`SkillReviewRecord`、`GeneratedScriptVersion`、现有版本管理。

### 需要扩展

| 对象 | 扩展方向 |
| --- | --- |
| `TemplatePattern` | 明确其职责是 StructurePattern（怎么组织内容）；新增参考稿引用关系，不再承担“文风”职责 |
| `ResearchBrief` | 从 `HotspotBrief` 演进：补充存疑信息、舆论观点、公众情绪、讨论背景、分阶段风险与来源证据 |
| `AngleCandidate` | 扩展为完整 Angle Card：支撑材料、缺失材料、撞题判断、风险 |
| `GeneratedScript` | 从“结构工作稿”改为完整可编辑稿；保留 editor / version / export 契约 |
| `SelectionRecord` | 区分 SelectedStructure 与 SelectedMaterials 记录，保留 Skill 版本追溯 |
| `RiskCheck` | 扩展为分阶段风险（Research / Angle / Material / Draft / Final） |

### 需要新增

| 对象 | 用途 |
| --- | --- |
| `WritingProject` | 一篇稿件的聚合根：topic、research、selected_angle、materials、selected_materials、selected_structure、reference_scripts、generation_settings、draft、review_annotations、risk_result、final_script |
| `MaterialCard` / `SelectedMaterials` | 第二轮定向研究产物与用户确认结果 |
| `ReferenceScript` | 真人参考稿资产（来自 manuscript-extractor 与人工保存） |
| `ReviewAnnotation` | AI 痕迹标注结果，与局部改写联动 |
| `GenerationSettings` | 账号类型、时长、语气、传播目标等轻量生成参数 |

### 准备废弃 / 降级

| 对象 / 能力 | 处理 |
| --- | --- |
| `HotspotBrief` | 保留兼容读取，逐步由 `ResearchBrief` 取代 |
| “结构工作稿”生成路径 | 降级为 fallback（仅当模型不可用时），不再是默认产物 |
| `HotspotStudio` 旧交互（先选 Skill） | 作废，并入新创作流程 |
| 全局“Skill 资产主线”文案 | 降级为 Skill 工厂内部信息 |

## 12. 最终验收

以《final-acceptance.md》为准。核心原则：

1. 默认首页是创作，不是 Skill 管理；打开后 10 秒内可以输入选题。
2. 输入选题后首先得到研究结果，且已确认事实与存疑信息明显区分。
3. 用户先选 Angle，再匹配 Structure；Angle 选定后进行第二次定向素材研究。
4. 没有任何现成 Skill 时也能完成生成。
5. AI 一次生成完整可编辑稿，human-writing 在生成阶段生效。
6. shuorenhua 默认用于 annotation；AI 味问题可直接触发现有局部改写。
7. GitHub / Codex Sync / Skill Gate 不阻塞普通创作；原有 Skill 工厂仍然能正常使用。
8. 至少使用 3 个真实娱乐 / 泛娱乐营销号选题跑完整路径。

## 13. 文档地图

| 文档 | 角色 | 状态 |
| --- | --- | --- |
| `README.md` | 仓库入口、快速开始 | 当前 |
| `docs/product-baseline.md` | **产品事实来源（本文件）** | 当前 |
| `docs/phase-roadmap.md` | 改造路线、代码差距、Phase 计划 | 当前 |
| `docs/final-acceptance.md` | 验收标准 | 当前 |
| `docs/skill-governance.md` | Skill 工厂治理规则（辅助能力） | 当前 |
| `docs/ui-component-selection.md` | UI 组件选型与页面映射 | 当前 |
| `docs/local-delivery.md` | 本机部署 / 运行手册 | 当前（操作） |
| `docs/llm-structured-output.md` | LLM 结构化输出技术说明 | 当前（技术） |
| `docs/postgres-persistence.md` | 持久化技术说明 | 当前（技术） |
| `docs/local-connector.md` | 兼容排障组件 | 历史 / 兼容 |
| `docs/local-mvp-status.md` | v1 状态快照 | 历史 |
| `evals/product-audit/operator-ux-audit.md` | 运营体验审计证据 | 历史（部分被本文档取代） |
| `evals/workbench/README.md` | 能力回归测试说明 | 当前（能力回归） |
| `../抖音热点脚本网站技术边界约束.md` | v1 技术边界 | 历史（技术约束仍部分有效） |
| `../抖音热点脚本网站v1产品方案蓝图.md` | v1 产品蓝图 | 历史 |
| `../抖音营销号业务SOP.md` | 业务运营 SOP（冲榜 / 铺量 / 账号） | 当前（业务） |
