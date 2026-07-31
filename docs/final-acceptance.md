# 依旧沉淀 v1 最终验收

这份文档只处理 v1 最后三道门禁，不扩展产品范围。

## 当前完成边界

代码闭环和本机视频模型链路已经可以通过自动化验收：

- 文本/字幕/转写输入到结构分析
- 模板沉淀
- 热点反推脚本
- 风控检查
- Markdown/JSON 导出
- 视频上传、FFmpeg、FunASR/PaddleOCR 工作进程
- 桌面和移动端核心 UI 流程

## 最终通过标准

`verify:workbench:final` 同时满足以下条件才算 v1 完成：

| 门禁 | 必须满足 |
| --- | --- |
| 代码闭环 | `acceptance`、依赖、LLM 离线 smoke、UI、前端构建、Python 编译均通过 |
| 视频模型链路 | `video-smoke` 报告通过 |
| 真实抖音链接 | 用授权的公开链接完成免登录真实下载验证 |
| 真实 LLM | 已配置真实 API Key/API Base/模型，并通过结构化 smoke |
| 人工复核 | 10 条热点脚本全部满足可拍、非纯复述、结构清晰、风控通过 |

## 推荐操作顺序

1. 启动工作台：

```bash
npm run workbench:start
```

2. 打开本机页面：

```text
http://127.0.0.1:5173/
```

3. 进入 `审核导出 -> 本机凭证配置`：

- 抖音公开链接提取无需配置登录态。
- 设置 LLM 模式为 `optional` 或 `required`。
- 填写模型名、API Base 和 API Key。
- 点击 `应用本机凭证`。

4. 进入 `审核导出 -> 人审记录`：

- 点击 `生成人审模板`。
- 对 10 条脚本逐条勾选：可拍、非复述、结构清晰、风险通过。
- 填写复核人/备注。
- 点击 `保存人审结果`。

5. 点击 `执行真实门禁`，或运行严格命令：

```bash
npm run verify:workbench:final -- --link '粘贴授权抖音分享文案或链接'
```

## 当前测试链接

```text
5.12 B@G.Iv ZMJ:/ 05/21 :7pm 品牌最好的宣传，其实早在行动里了# 奢侈品 # 时尚 # gucci # 肖战 # 宋威龙  https://v.douyin.com/gk_7aLCc3SU/ 复制此链接，打开Dou音搜索，直接观看视频！
```

系统应解析为：

```text
https://v.douyin.com/gk_7aLCc3SU/
```

## 状态报告

每次运行都会更新：

```text
evals/workbench/status-report.md
evals/workbench/status-report.json
```

`passed=False` 且 `code=True`、`video=True`、`external=False` 时，说明代码和视频链路已就绪，剩余问题只在外部验收输入。

## 安全边界

- API Key 只通过本机 UI 或当前 shell 环境传入。
- 不要把 API Key 写入仓库文件。
- 状态报告只显示是否配置和脱敏提示，不输出明文密钥。
