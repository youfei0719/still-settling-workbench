# 依旧沉淀

短视频写作 Skill 工作台。依旧沉淀从可验证的授权来源取得真实稿件，提炼可复用的写法结构；经过评测和人工复核后，用户可手动发布到自己的 GitHub Skill 仓库或仅保存在本机。

## Skill 资产主线

`授权来源 -> 真实稿件 -> 结构沉淀 -> 质量复核 -> 正式版本 -> 发布与加载`

每一步都有明确边界：未取得真实稿件不会拆解，未通过复核的候选 Skill 不会被发布，发布始终需要用户手动确认。

## Local setup

```bash
cp .env.example .env
cp .env.workbench.example .env.workbench.local
npm install
uv sync --project backend
npm run workbench:start
```

打开 `http://127.0.0.1:5173/`，进入“系统诊断”完成首次配置：模型连接，以及连接已有 GitHub 仓库、创建 GitHub 仓库或仅本地保存三种发布方式之一。抖音会话为可选配置。

密钥与 Cookie 不会写入项目文件。支持系统钥匙串时会保存到操作系统安全存储；否则仅在当前服务运行期间有效。

## Open-source release check

```bash
uv run --project backend python scripts/verify-open-source-release.py
```

检查通过后，在新的空 Git 仓库中提交代码。不要推送当前模板仓库的既有 Git 历史。

## License

MIT. This project retains the upstream FastAPI template copyright notice in [LICENSE](LICENSE).
