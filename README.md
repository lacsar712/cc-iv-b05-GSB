# 光伏组串IV扫描台

扫描员提交组串开路电压、短路电流与填充因子。写入后走 PostgreSQL 通知通道叫醒独立工人，工人不轮询空转。填充因子不低于 0.72 为合格，否则衰减。页面是 Vue 3。

## 交班本

离岗前从顶栏进「交班本」专页：页内分盖章钮、旧本目录、正文预览三块，未选本时预览显示"本子还是空的"。按下盖章那一瞬取当时总单数、合格数、衰减数三张计数章，同一事务写进新本正文并落库进旧本目录；盖上以后在线单据再变也刮不掉本上的字，回看旧本停在盖章当时。一张单都没有时可盖出全零本。观察员（watcher）只许翻已盖的本，接口层同样拒绝其盖章。

- `GET /api/handover-books`：旧本目录（登录即可）
- `POST /api/handover-books`：盖章立新本（仅 scanner）

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
