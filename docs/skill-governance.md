# 写作 Skill 治理

## 生命周期

- `candidate`：从授权来源沉淀，不能路由、热点生成或发布。
- `active`：通过真实模型发布评测并获内容主审批准，可路由、导出和发布。
- `paused`：保留历史和证据，但不参与路由或发布。
- `retired`：永久停止分发，保留历史版本供追溯。

历史启用资产在迁移后统一降为 `candidate`；已有停用资产变为 `paused`。

## 正式发布门槛

每条 Skill 需要至少三个授权来源、真实模型评测通过和至少一条主审批准记录。发布评测必须在 `WORKBENCH_LLM_MODE=required` 下运行：

```bash
npm run eval:skills:release
```

该命令从三条候选 Skill 生成固定集报告：72 条路由、30 条成稿 brief（每条三次运行）、20 条事实安全用例。它需要可用模型凭据和完成的 `evals/workbench/skill-human-review.json`；它不会接受 offline fallback 作为通过证据。

主审将报告路径填入 Skill 治理面板后才能批准为 `active`。后端只读取 `evals/workbench/` 内的报告，并校验 `required` 模式、模型名称、每条 Skill 的门槛指标和盲审样本数，忽略客户端提交的“评测通过”字段。

## 团队同步

发布包包含总路由器和每条正式 Skill 的独立目录。通过以下安装器写入 Codex 的直属 Skill 目录：

```bash
python3 scripts/install_atomic_skills.py <workbench-skill-pack-url> ~/.codex/skills
```

安装器仅替换自身状态文件中记录的 `douyin-writing-*` 目录；若同名目录不是此前由本系统安装，会拒绝覆盖。路由器只处理选择、比较或解释团队写法，原子 Skill 独立触发普通写作请求。
