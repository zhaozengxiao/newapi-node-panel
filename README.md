# newapi-node-panel

[QuantumNous/new-api](https://github.com/QuantumNous/new-api) 渠道/节点管理 Web 面板。
解决"自动禁用的渠道（status=3）需要手动逐个恢复、key 全禁后渠道死锁无法自动恢复"的日常运维痛点。

## 功能

- **渠道看板**：全部渠道状态一览（1 启用 / 2 手动禁用 / 3 自动禁用），状态筛选 + 关键字搜索，30s 自动刷新
- **一键启用**：`enable_full` = 恢复渠道**全部 key**（`POST /api/channel/multi_key/manage` 的 `enable_all_keys`）+ 渠道启用，一步到位
- **批量操作**：一键启用全部"自动禁用"渠道（含 key 或仅渠道级）
- **定时规则**：傻瓜式配置（选频率 + 时间点，自动翻译成 cron），支持
  - `enable_full` 一键启用（含 key）
  - `enable` / `disable` 渠道启停
  - `enable_keys` 恢复全部 key
  - `test` 渠道测试
  - `checkup` 巡检（恢复 key → 测试 → 通过则启用）
- **操作日志**：全部操作留痕（内存 + `data/ops.log` 持久化）

典型场景：免费模型渠道每日配额 00:00 UTC（08:00 CST）重置后，配置一条 `每天 08:05 一键启用全部自动禁用` 的规则，从此无需手动救。

## 架构

- Python 3.12 + Flask + APScheduler（进程内定时调度），单容器部署
- **token 不硬编码**：服务通过 psycopg2 实时读取 postgres 的 `users.access_token`（带 TTL 缓存），DB 重建 / token 轮换后零维护
- 管理操作全部走 new-api HTTP API（`/api/channel/*`），不直写数据库
- 部署于 new-api 同一 Docker 网络，经 `http://new-api:3000` 调用

## 快速开始

```bash
# 1. 准备（需与 new-api/postgres 同机，能加入其 docker 网络）
git clone https://github.com/zhaozengxiao/newapi-node-panel.git
cd newapi-node-panel
cp .env.example .env        # 填入 postgres 的 POSTGRES_PASSWORD
vim docker-compose.yml      # 如网络名不同，改 networks 的 external 名

# 2. 构建启动
docker compose up -d --build

# 3. 访问
# http://<host>:3434
```

前置条件：new-api 与 postgres 容器需在同一 docker 网络（默认 `new-api_new-api-network`）；`POSTGRES_PASSWORD` 与 new-api 的 postgres 容器一致。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `PG_HOST` | `postgres` | postgres 容器名/hostname |
| `PG_PORT` | `5432` | postgres 端口 |
| `PG_USER` | `root` | postgres 用户 |
| `PG_PASSWORD` | — | **必填**（.env），postgres 密码 |
| `PG_DB` | `new-api` | new-api 数据库名 |
| `NEWAPI_BASE` | `http://new-api:3000` | new-api 容器内地址 |
| `DATA_DIR` | `/data` | 规则/日志持久化目录（volume） |

## 自带 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/channels` | 渠道列表 |
| GET | `/api/channels/<id>` | 渠道详情 + key 状态 |
| POST | `/api/channels/<id>/enable` / `disable` | 渠道启用 / 禁用 |
| POST | `/api/channels/<id>/enable_keys` | 恢复全部 key（enable_all_keys） |
| POST | `/api/channels/<id>/enable_full` | 一键启用（恢复全部 key + 渠道启用） |
| POST | `/api/channels/<id>/test` | 渠道测试（可选 `{"model":"..."}`） |
| POST | `/api/channels/<id>/key/<idx>/enable` / `disable` | 单 key 启停 |
| POST | `/api/channels/batch` | 批量 `{"action":"...","target":{"ids":[] 或 "filter":"auto_disabled"}}` |
| GET/POST/PUT/DELETE | `/api/rules`、`/api/rules/<id>` | 定时规则 CRUD |
| POST | `/api/rules/<id>/trigger` | 立即执行规则 |
| GET | `/api/logs` | 操作日志 |

定时规则结构：

```json
{
  "name": "kenari每日启用",
  "cron": "5 8 * * *",
  "action": "enable_full",
  "target": {"filter": "auto_disabled"}
}
```

`target` 支持 `{"ids":[76,57]}`（指定渠道）或 `{"filter":"all|auto_disabled|disabled"}`（按状态筛选）。

## License

MIT
