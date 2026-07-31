# 本机 Postgres 持久化验证

## 已验证状态

工作台已经具备 PostgreSQL 持久化基础：

- SQLModel 表模型已加入 `backend/app/models.py`
- Alembic 迁移已加入 `backend/app/alembic/versions/7c2d8f31a9b4_add_workbench_persistence_tables.py`
- API 已接入可选持久化：数据库可用时写入数据库，不可用时自动降级到内存模式
- 验证脚本已加入 `backend/scripts/verify_workbench_persistence.py`

当前开发机已完成真实 PostgreSQL 验证：

- Docker Compose 已启动 `db` 服务并通过健康检查。
- Alembic 已迁移到最新工作台表结构。
- 已写入分析结果、模板资产和生成脚本，并能从数据库读取 overview。
- API 使用 `WORKBENCH_DB_MODE=auto` 重启后仍能读取已保存记录。

## 已可运行的结构烟测

无需 Postgres，使用 SQLite 内存库验证表模型和保存适配层：

```bash
cd /path/to/douyin-script-workbench/backend
uv run python scripts/verify_workbench_persistence.py --mode sqlite
```

期望输出包含：

```text
workbench_persistence_ok mode=sqlite
```

## Postgres 可用后的验证命令

需要复测或在其他机器部署时，先确认 `.env` 中的数据库配置：

```text
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_DB=app
POSTGRES_USER=postgres
POSTGRES_PASSWORD=...
```

然后执行：

```bash
cd /path/to/douyin-script-workbench/backend
uv run python scripts/verify_workbench_persistence.py --mode configured --migrate
```

这条命令会：

1. 运行 Alembic 迁移到最新版本。
2. 写入一条分析记录。
3. 写入一组热点生成脚本。
4. 从数据库读取 overview 数据。
5. 输出模板数、脚本数和首个内容角度。

## 通过标准

- 命令输出 `workbench_persistence_ok mode=configured`
- `templates` 大于 0
- `scripts` 大于 0
- `overview_templates` 大于 0
- 重启后端后，`GET /api/v1/script-workbench/overview` 仍能读到数据库记录

## 注意

`scripts/dev-workbench-api.py` 默认使用 `WORKBENCH_DB_MODE=auto`：数据库可用时持久化，不可用时自动降级到内存模式。需要强制轻量演示时可设为 `off`。
