# price-platform

基于 Kubernetes 的云原生 RPA 价格监控平台（毕业设计实现）。

- 调度：PostgreSQL 行锁 + 30s tick + 1s 延时重试提升
- 队列：Redis Stream 消费组（ACK / PEL / XAUTOCLAIM）
- 执行：Playwright（Chromium）+ 站点适配器，任务级 BrowserContext 隔离
- 可靠：300s 超时、3 次重试/5s 间隔、DLQ、reaper 自愈
- 观测：Prometheus + Grafana + EFK（Fluent Bit → Elasticsearch → Kibana）
- 弹性：KEDA 按 Stream lag 扩缩容
- 前端：Vue 3 + Element Plus + ECharts

## 本地开发

```bash
# 依赖：Docker Desktop、Python 3.10+、Node 20+
python -m venv .venv && .venv\Scripts\pip install -e ".[dev,worker]"
copy .env.example .env            # 修改数据库/Redis 端口与 JWT secret
docker compose -f deploy/compose/docker-compose.dev.yml up -d postgres redis
python -m alembic upgrade head
python scripts/seed.py --interval 1800
python scripts/dev.py up          # mock-shop + api + scheduler + reaper + worker
python scripts/dev.py status
python scripts/dev.py down
```

打开 <http://127.0.0.1:8000/docs> 查看 API；默认账号 `admin / admin123`。

## 测试

```bash
pytest tests/unit -q
pytest -m integration -q          # 需要 Postgres/Redis 已启动
```

## Kubernetes（k3d 1 server + 2 agents）

见 `docs/DEPLOY.md` 与 `deploy/` 目录。
