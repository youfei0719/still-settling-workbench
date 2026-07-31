# 依旧沉淀 v1 本机交付说明

## 交付定位

这是一个本机/内网使用的内部 AI 内容生产工作台，不是公网 SaaS，也不是营销 landing page。

v1 只交付一条生产闭环：

```text
抖音链接/上传输入
-> 视频、字幕或文案提取
-> 脚本结构分析
-> 模板资产沉淀
-> 热点反推脚本
-> 风控检查
-> Markdown/JSON 导出
```

主界面固定为五个页面：

1. 链接分析台
2. 分析工作区
3. 模板资产库
4. 热点反推室
5. 审核导出

“审核导出”页包含 v1 外部门禁面板，用来跟踪真实抖音链接、真实 LLM 和人工质量复核三项最终验收状态。

## 明确不做

- 不做自动发布、冲榜、UID 绑定、平台数据回收或客户结案。
- 不做公网 SaaS、多租户、付费、账号资产导入或运营交接后台。
- 不把离线 fallback 输出伪装成真实模型输出。
- 不抓取或分析未授权、非公开、不可合法使用的第三方内容。

## 快速启动

首次准备模型环境：

```bash
cd /path/to/douyin-script-workbench
npm run model-env:workbench
```

后端：

```bash
cd /path/to/douyin-script-workbench
WORKBENCH_MODEL_WORKER_PYTHON=.venv-model/bin/python .venv/bin/python scripts/dev-workbench-api.py
```

前端：

```bash
cd /path/to/douyin-script-workbench
npm run dev --workspace frontend -- --host 127.0.0.1
```

日常使用推荐一条命令启动前后端：

```bash
cd /path/to/douyin-script-workbench
npm run workbench:start
```

这个命令会用本机 `screen` 启动独立后台会话，并自动健康检查 API 和前端。常用控制命令：

```bash
npm run workbench:status
npm run workbench:logs
npm run workbench:stop
```

如果前端或 API 已经由其他命令启动，`workbench:start` 会复用现有健康服务；`workbench:status` 会标记为 `managed` 或 `unmanaged`，`workbench:stop` 只停止由脚本管理的 `screen` 会话，不会强杀用户手动启动的进程。

打开：

```text
http://127.0.0.1:5173/
```

当前本机健康检查：

| 服务 | 地址 |
| --- | --- |
| 前端 | `http://127.0.0.1:5173/` |
| API | `http://127.0.0.1:8000/api/v1/script-workbench/overview` |

本机 shell 可能配置了代理，检查本地服务时使用：

```bash
curl --noproxy '*' http://127.0.0.1:8000/api/v1/script-workbench/overview
```

## Docker / PostgreSQL

完整本机栈：

```bash
docker compose up --build
```

PostgreSQL 持久化验证：

```bash
cd /path/to/douyin-script-workbench/backend
uv run python scripts/verify_workbench_persistence.py --mode configured --migrate
```

当前开发机已验证 Docker PostgreSQL 迁移、写入、读取和 API 重启后的数据保留。没有数据库时，可使用 `WORKBENCH_DB_MODE=off` 做轻量验证。

## 环境变量

样例文件：

```text
.env.workbench.example
```

| 变量 | 用途 |
| --- | --- |
| `WORKBENCH_MEDIA_DIR` | 视频、音频、关键帧临时保存目录 |
| `WORKBENCH_DB_MODE` | `auto` / `off`，默认优先 PostgreSQL |
| `WORKBENCH_LLM_MODE` | `offline` / `optional` / `required` |
| `WORKBENCH_LLM_MODEL` | LiteLLM 模型名 |
| `WORKBENCH_LLM_API_BASE` | OpenAI 兼容 API 或中转站地址 |
| `WORKBENCH_LLM_API_KEY` | 模型 API Key；脚本会映射到 `OPENAI_API_KEY` |
| `WORKBENCH_ASR_MODE` | FunASR 开关：`auto` / `off` / `required` |
| `WORKBENCH_OCR_MODE` | PaddleOCR 开关：`auto` / `off` / `required` |
| `WORKBENCH_MODEL_WORKER_PYTHON` | 指定运行 FunASR/PaddleOCR 的独立 Python |
| `WORKBENCH_ALLOW_SYSTEM_MODEL_PYTHON` | 是否允许回退到 macOS 系统 Python；默认关闭 |
| `WORKBENCH_DOUYIN_DOWNLOADER_DIR` | `jiji262/douyin-downloader` 本地仓库目录 |
| `WORKBENCH_DOUYIN_DOWNLOADER_CMD` | 自定义 douyin-downloader 命令 |
| `WORKBENCH_DOUYIN_PUBLIC_ATTEMPTS` | 公开链接提取的自动尝试次数，默认 `2` |
| `WORKBENCH_DOUYIN_RETRY_DELAY_SECONDS` | 自动重试的基础等待秒数，默认 `1` |

公开链接提取不读取浏览器 Cookie，也不需要登录抖音。不要把 API Key 写进仓库。

## 抖音链接边界

工作台支持粘贴纯短链，也支持粘贴完整抖音分享文案。后端会自动提取其中的 `douyin.com` 链接。

已用以下样本验证：

```text
5.12 B@G.Iv ZMJ:/ 05/21 :7pm 品牌最好的宣传，其实早在行动里了# 奢侈品 # 时尚 # gucci # 肖战 # 宋威龙  https://v.douyin.com/gk_7aLCc3SU/
```

当前结果：

| 项目 | 结果 |
| --- | --- |
| 短链提取 | 成功提取为 `https://v.douyin.com/gk_7aLCc3SU/` |
| 下载器 | 可调用 |
| 抖音响应 | 空 `200` 或短链解析临时失败 |
| 系统分类 | `public_access_unavailable` |
| 用户下一步 | 系统会在本次提交内自动重试；仍失败时稍后直接重试同一公开链接 |

## 视频任务边界

默认视频上传是轻量流程：

1. 保存视频到临时目录。
2. 用 FFmpeg 抽音频。
3. 用 FFmpeg 抽 OCR 关键帧。
4. 不自动启动 FunASR/PaddleOCR，避免首次模型下载或原生库异常阻塞上传。
5. 用户明确点击后台 ASR/OCR 后，模型在隔离子进程运行；未配置 `WORKBENCH_MODEL_WORKER_PYTHON` 时只返回兜底提示，不默认调用系统 Python。

模型提取成功后，系统只长期保存转写、分析结果、模板资产和生成记录；原始视频、音频和关键帧会自动清理。

## 验收命令

核心闭环：

```bash
npm run verify:workbench
```

当前覆盖：

| 验收项 | 当前结果 |
| --- | --- |
| 30 条文本样本 | 30/30 |
| 10 个热点样本 | 10/10 |
| 风控样本 | 3/3 |
| 完整分享文案链接提取 | 通过 |
| 依赖诊断 | required 2/2，optional 6/6 |
| Promptfoo | 3/3 |
| 前端构建 | 通过 |
| 桌面/移动 UI | 4/4 |
| Python 编译 | 通过 |

视频轻量 smoke：

```bash
npm run video-smoke:workbench
```

自有中文口播和硬字幕完整 smoke：

```bash
npm run video-smoke:workbench:models
```

带模型环境的完整回归：

```bash
npm run verify:workbench:models
```

真实模型 smoke：

```bash
npm run llm-smoke:workbench
```

如果已经配置真实模型，并要求没有真实模型调用就失败：

```bash
WORKBENCH_LLM_MODE=optional \
WORKBENCH_LLM_MODEL=openai/gpt-4.1-mini \
WORKBENCH_LLM_API_KEY=你的中转站或 OpenAI 兼容 Key \
npm run llm-smoke:workbench -- --expect-model
```

外部门槛检查：

```bash
npm run external-gates:workbench
```

这个命令会检查三件事：是否具备真实抖音公开链接下载条件、是否具备真实 LLM 调用条件、是否已经完成人工脚本质量复核。下载检查不要求 Cookie；模型 key 或人审文件缺失时会写出明确报告：

网站内也可以在“审核导出 -> v1 外部门禁”刷新同一组状态，并生成 `evals/workbench/human-review-template.json` 人审模板；模板会优先带入当前生成脚本的标题和内容角度。

```text
evals/workbench/external-gates-report.json
```

当前整体状态汇总：

```bash
npm run workbench:summary -- --link 'https://v.douyin.com/...'
```

它会汇总本机服务状态、组件能力、核心验收报告、视频 smoke 报告和三项外部门禁，并生成：

```text
evals/workbench/status-report.json
evals/workbench/status-report.md
```

准备好授权的公开抖音链接后，可执行真实链接验收：

```bash
npm run external-gates:workbench -- --link 'https://v.douyin.com/...' --run-link
```

要生成人审模板：

```bash
npm run external-gates:workbench -- --write-human-review-template
```

填写模板后复核：

```bash
npm run external-gates:workbench -- --human-review-file evals/workbench/human-review-template.json
```

## 当前外部验收门槛

| 任务 | 当前状态 | 完成条件 |
| --- | --- | --- |
| 真实授权抖音链接下载 | 待外部条件 | 公开链接以免登录方式跑通下载 -> ASR/OCR -> 分析 -> 脚本 |
| 真实 LLM 质量 | 待外部条件 | 配置真实 API key/base 后，运行 `llm-smoke --expect-model` 并人工抽检输出 |
| 人工脚本质量复核 | 待人工 | 对 10 个热点输出按“可拍摄、非复述、结构清晰、风控合格”打分 |

## 数据边界

| 数据 | v1 保存策略 |
| --- | --- |
| 原始视频 | 临时保存；成功生成统一转写后自动清理 |
| 抽取音频 | 临时保存；成功生成统一转写后自动清理 |
| OCR 关键帧 | 临时保存；成功生成统一转写后自动清理 |
| 转写文本 | 长期保存 |
| 结构分析 | 长期保存 |
| 模板资产 | 长期保存 |
| 生成脚本 | 长期保存 |
| 链接诊断记录 | 只保存链接、错误码、建议动作和下载器结果，不保存浏览器会话或 Cookie |

## 风控边界

- 明星事件不输出未经证实的事实断言。
- 不生成隐私、人身攻击、恶意引战、低俗擦边、未成年人高敏内容。
- 对竞品视频只学习结构和表达策略，不做逐句仿写。
- 风控是生产辅助，不替代人工审核。

## 故障兜底

| 现象 | 处理 |
| --- | --- |
| 链接解析失败 | 上传视频、字幕或粘贴文本 |
| 公开链接暂时不可用 | 系统已自动重试；稍后再次提交同一链接，或上传已获授权的视频/字幕/转写文本 |
| 视频无法抽音频 | 上传字幕或转写文本 |
| FunASR 未安装或失败 | 使用字幕/转写文本兜底 |
| PaddleOCR 未安装或失败 | 使用字幕/转写文本兜底 |
| LLM 调用失败 | `optional` 模式自动 fallback；`required` 模式失败 |
| Docker 不可用 | 使用轻量本机模式 |
