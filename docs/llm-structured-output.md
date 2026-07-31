# LiteLLM + Instructor 结构化输出

## 当前状态

工作台已接入可选 LLM 管线：

- 默认使用 `offline` 模式，走 deterministic fallback，保证本机无 API key 也能运行。
- `optional` 模式会优先尝试 LiteLLM + Instructor，失败后自动回退到 fallback。
- `required` 模式会强制使用模型；模型失败时直接报错，适合正式联调。
- 新增状态接口：`GET /api/v1/script-workbench/llm-status`
- 前端顶部会显示当前模型模式：离线结构化、模型优先、模型必需。

## 环境变量

可在 `.env` 或启动命令里配置：

```text
WORKBENCH_LLM_MODE=offline
WORKBENCH_LLM_MODEL=openai/gpt-4.1-mini
WORKBENCH_LLM_API_BASE=
WORKBENCH_LLM_API_KEY=
WORKBENCH_LLM_TEMPERATURE=0.2
WORKBENCH_LLM_MAX_RETRIES=1
```

模式说明：

| 模式 | 行为 | 适合场景 |
| --- | --- | --- |
| `offline` | 不调用模型，只用本地 fallback | 默认开发、本机演示 |
| `optional` | 有模型就用，失败自动回退 | 接中转站/API 初期 |
| `required` | 必须调用模型，失败报错 | 正式联调和质量测试 |

## 使用 LiteLLM

后端已安装：

- `litellm`
- `instructor`

如果使用 OpenAI 兼容接口，可按对应服务要求设置环境变量，例如：

```bash
export WORKBENCH_LLM_MODE=optional
export WORKBENCH_LLM_MODEL=openai/gpt-4.1-mini
export WORKBENCH_LLM_API_KEY=...
```

如果使用中转站：

```bash
export WORKBENCH_LLM_MODE=optional
export WORKBENCH_LLM_MODEL=openai/your-model-name
export WORKBENCH_LLM_API_BASE=https://your-compatible-endpoint/v1
export WORKBENCH_LLM_API_KEY=...
```

## Smoke Test

先验证 schema 和 fallback：

```bash
npm run llm-smoke:workbench
```

配置真实模型后验证真实调用：

```bash
WORKBENCH_LLM_MODE=optional \
WORKBENCH_LLM_MODEL=openai/gpt-4.1-mini \
WORKBENCH_LLM_API_KEY=your-api-key \
npm run llm-smoke:workbench -- --expect-model
```

报告输出：

```text
evals/workbench/llm-smoke-report.json
```

然后启动后端：

```bash
cd /path/to/douyin-script-workbench
python3 scripts/dev-workbench-api.py
```

## 结构化输出边界

当前通过 Pydantic schema 约束：

- `StructuredAnalysisOutput`
- `StructuredHotspotOutput`

模型输出必须包含：

- 视频脚本结构分析字段
- 热点 brief
- 3-5 个生成脚本版本
- 风控结果
- 分镜建议
- 字幕节奏

如果模型输出不符合 schema：

- `optional` 模式：回退到 deterministic fallback
- `required` 模式：抛出错误，便于测试 prompt 和 schema

## 下一步

后续接 Promptfoo 时，应把以下样本固定为回归用例：

- 结构分析样本
- 热点生成样本
- 风控高风险样本
- 明星隐私/未经证实事实样本
