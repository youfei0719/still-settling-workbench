# Contributing

谢谢你关注依旧沉淀。

## Before Opening a Pull Request

- 先在 Issue 说明需要解决的问题、复现步骤或使用场景。
- 保持每个 Pull Request 聚焦一个可验证的改动，并补充相应测试。
- 不要提交 API Key、Cookie、真实稿件、Skill 资产、评测产物或本机配置文件。
- 修改发布、模型或来源提取逻辑时，说明对本机数据与隐私的影响。

## Local Checks

按照 [README](README.md) 完成本机启动后，至少运行：

```bash
npm run build --workspace frontend
uv run --project backend python scripts/verify-open-source-release.py
```

提交前确认不会把个人 GitHub 地址、密钥、Cookie 或本机绝对路径带入暂存区。
