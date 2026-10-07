# 光伏组串IV扫描台

扫描员提交组串开路电压、短路电流与填充因子。写入后走 PostgreSQL 通知通道叫醒独立工人，工人不轮询空转。填充因子不低于 0.72 为合格，否则衰减。页面是 Vue 3。

## 技术栈

- 后端：Litestar、Uvicorn、psycopg 同步写入
- 工人：`LISTEN/NOTIFY` 唤醒后认领
- 前端：Vue 3、Vite、nginx 反代 `/api`

## 端口

| 服务 | 地址 |
|------|------|
| 页面 | http://localhost:3202 |
| 接口 | http://localhost:8202 |
| PostgreSQL | localhost:54402（库名 `pvivscan`） |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| scanner | scan123456 | 可提交 |
| watcher | watch123456 | 只读 |

## 启动

```bash
cd projects/22-pv-string-iv-scan
docker compose up --build
```

健康检查：`GET http://localhost:8202/api/health`

## 种子

| 组串 | 填充因子 | 结论 |
|------|----------|------|
| 阵列A-串03 | 0.78 | 合格 |
| 阵列B-串11 | 0.61 | 衰减 |

## 交班本

运维离岗前要把当时的三张计数（在线单据总数 / 合格 / 衰减）盖章进交班本。

- 顶栏「交班本」进入专页，页内三块：盖章钮、旧本目录、正文预览。
- 只有扫描员（scanner）能盖章；观察员（watcher）只能翻看已盖的本。
- 按下盖章的一瞬，在单个 `REPEATABLE READ` 事务内取计数与全部在线单据，连同渲染好的正文一起写入 `shift_handover_books` 表（计数列 + `body` 文本 + `snapshot` jsonb）。
- 本上的字落库即定型：之后在线单据再增再变，旧本的计数、正文、快照都不会被刮掉。
- 一张单都没有时也可以盖，盖出全零本。
- 旧本目录为空时，目录区显示「本子还是空的」。

接口：

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/api/handover-books` | writer | 盖章，201 返回新本全文 |
| GET | `/api/handover-books` | 登录 | 旧本目录（不含正文） |
| GET | `/api/handover-books/{id}` | 登录 | 单本正文与快照 |
