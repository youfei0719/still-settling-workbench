# 更新记录

本文件记录产品方向与能力的阶段性更新。当前产品事实来源见
[docs/product-baseline.md](docs/product-baseline.md)，改造路线见
[docs/phase-roadmap.md](docs/phase-roadmap.md)。

## 2026-09-13 — 创作工作台 v2（Phase 1–4）

这次更新的重点不是加功能，而是**把产品主线从「Skill 资产管理」改回「每天写稿」**，
并给生成过程加上事实与证据纪律。

### 1. 产品定位与信息架构（Phase 1）

- 默认首页从「沉淀 Skill」改为**新建稿件**：输入选题（可附材料）→ 开始研究。
- 主导航重排为：`＋新建稿件 / 稿件项目` —— `结构库 / 参考稿库` —— `Skill 工厂 / 系统设置`。
- 引入 `WritingProject` 概念：一篇稿件贯穿 8 步
  （选题 → 研究 → 角度 → 素材 → 结构 → 成稿 → 审稿 → 导出），步骤状态可前进 / 后退 / 保留。
- 原有能力（链接解析、转写、结构分析、Skill 治理、GitHub 发布、Codex 同步）全部保留，
  收进 **Skill 工厂 / 系统设置**，不再阻塞普通写稿；旧组件只降级、不删除。
- Phase 1 未做数据库改造：`WritingProject` 只保存在前端会话中。

### 2. 联网研究（Phase 2）

- 新增 `POST /research/briefs`：联网研究 + 4–8 个内容角度候选，**不返回任何 Skill / 结构匹配**。
- 研究结果严格区分 **已确认事实 / 存疑信息 / 观点与争议**，来源带 URL、发布方与时间。
- **逐条事实可追溯到具体来源**：`verified_claims[{id, claim, source_ids, confidence, note}]`；
  没有来源支持的说法自动降级为「待核验」，不再出现在「已确认事实」里。
- 未完成联网核验时，界面明确显示「当前为研究预览，尚未完成联网事实核验」，
  不再把用户输入标成事实。
- 角度改为**强制人工决策**：必须选择推荐角度或自定义角度（`SelectedAngle`）才能继续；
  「暂不设定」已移除。
- 结构匹配与研究会话解耦：只有确认角度后进入结构步骤时，才按需请求结构推荐。

### 3. 素材与结构（Phase 3）

- 新增 `POST /research/materials`：围绕已选角度的**第二轮定向研究**
  （query = 选题 + 已选角度 + 研究简报 + 角度缺失证据），带停止条件，复用第一轮已打开来源。
- 新增 `MaterialCard`：`type`（fact / quote / opinion / case / data / background / comparison）、
  来源与日期、可访问链接、`relevance_to_angle`、`suggested_usage`、`risk`；
  没有可访问来源时一律标 `uncertain`，不伪装成已核实。
- 素材由用户**显式选择**（使用 / 不使用，支持全选与取消），`SelectedMaterials` 才进入后续环节；
  未选素材时提示「继续写作可能主要依赖通用推理」，但不阻断。
- 新增 `POST /structures/recommend`：基于 **已选角度 + 已选素材** 推荐 1–3 个结构，
  每个结构说明「为什么适合这个角度 / 素材如何填进结构 / 可能材料不足的地方」；
  **通用写作骨架始终可用**，Skill 库为空时也能正常写稿。
- 修复已发布 Skill 骨架不可读的问题：把整段 `writing_method` 解析成 4 步可读推进骨架。

### 4. 完整成稿（Phase 4）

- 新增 `POST /scripts/generate`：一次生成**一篇**完整可编辑主稿
  （标题 + 标题候选 + 完整口播 + 分镜建议 + 字幕节奏 + 互动引导 + 风险提示），
  不再让用户在多个「结构工作稿」之间选择。
- **Allowed Evidence 证据边界**：正文中的事实性内容只能来自
  ① 用户明确输入 ② 已选素材 ③ 与已选素材关联且逐条核验过的事实；
  禁止使用存疑说法、未选素材、无来源信息与模型记忆补充的事实。
- **Evidence Check**：生成后逐句核对，无法映射到证据的陈述会被删除或降级为非确定表达，
  并记录在 `evidence_check.unsupported_claims`；
  同时保证正文永不为空、绝不含占位符。
- `GeneratedScript` 扩展 `used_material_ids / used_claim_ids / material_gaps /
  evidence_map / evidence_check / structure_coverage / evidence_policy`，
  系统内部可追溯「这篇稿的事实依据来自哪里」（不进入口播正文）。
- **Material Gap 只在正文之外**：证据不足时少写或不写该论点，缺口以「缺口 + 处理」记录，
  不允许留下 `【这里补案例】` 之类占位。
- 成稿步骤提供轻量生成设置（账号类型 / 参考时长 / 语气 / 传播目标，均有默认值）、
  textarea 编辑器、字数与预计时长、版本保存与恢复。

### 5. 模型通道

- 普通调用（完整成稿、结构推荐、证据复核）与联网研究**可以走不同通道**：
  - `WORKBENCH_LLM_TRANSPORT`：普通调用通道（如中转 `litellm`）。
  - `WORKBENCH_RESEARCH_TRANSPORT` + `WORKBENCH_RESEARCH_CODEX_AUTH_MODE`：联网研究通道，
    必须使用能真正执行 Web 检索的通道。
- 只返回文本、不产生 `web_search_call` 的中转**不能用于研究**，
  否则会把模型记忆伪装成「已联网核验」。详见 [docs/local-delivery.md](docs/local-delivery.md)。
- 通道错误对用户只显示一句可读说明（如「本机 Codex 用量已达上限」），不再泄漏底层日志。

### 6. 验证

- 后端单元测试 **87 项通过**（新增研究 / 素材 / 成稿契约测试，含证据边界与对抗用例）。
- Playwright 桌面 + 移动端 **20 passed / 6 skipped**；前端构建通过。
- 三个真实选题（娱乐人物 / 品牌商业 / 泛娱乐社会）端到端：真实联网研究 + 真实模型生成，
  平均生成约 50–65 秒，全流程约 5 分钟。
- 对抗测试：故意选择证据不足的角度，模型没有为写完文章而编造事实。

### 7. 尚未开始

- Phase 5：去 AI 味（生成阶段 `human-writing`、审稿阶段 `shuorenhua` 标注 + 局部改写）。
- Phase 6：Reference Library（真人参考稿检索）。
- `WritingProject` 数据库持久化仍在后续阶段讨论。
