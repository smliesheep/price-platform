# price-platform

基于 Kubernetes 的云原生 RPA 价格监控平台（毕业设计实现）。

调度与执行解耦：数据库行锁保证定时投递，Redis Stream 消费组保证至少一次，三层幂等收敛为"有效一次"，
Worker 用 Playwright 驱动真实浏览器抓取，KEDA 按队列深度弹性伸缩，Prometheus/Grafana/EFK 提供完整可观测性。

## 架构

```
浏览器 ──▶ Ingress(traefik) ──▶ web(Vue3) / api(FastAPI ×2)
                                   │
api ──▶ PostgreSQL ◀── scheduler(30s tick + 1s 重试提升)
api ──▶ Redis Stream ◀── reaper(孤儿回收/补投)
              │
              └── XREADGROUP ──▶ worker ×N(Playwright) ──▶ Mock 商城/目标站点
                                        │
                                        └── 写回 PostgreSQL（价格/状态/Worker 归属）

旁路：Prometheus → Grafana；Pod stdout → Fluent Bit → Elasticsearch → Kibana；Alertmanager → API 落库
```

## 技术栈

| 层 | 选型 |
|---|---|
| 调度 | PostgreSQL `FOR UPDATE SKIP LOCKED` + advisory lock，30s tick |
| 队列 | Redis Stream 消费组 + ZSET 延时重试 + DLQ |
| 执行 | Playwright(Chromium) / HTTP 双适配器，任务级 BrowserContext |
| 存储 | PostgreSQL 16（7 张表，唯一键幂等） |
| 接口 | FastAPI + JWT，28 个端点 |
| 前端 | Vue 3 + TypeScript + Element Plus + ECharts |
| 可观测 | Prometheus + Grafana + Alertmanager + EFK |
| 弹性 | KEDA（Redis Streams lag） |
| 部署 | k3d 1 server + 2 agents，containerd |

## 快速开始（本地）

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev,worker]"
copy .env.example .env                 # 按需改端口/密码

docker compose -f deploy/compose/docker-compose.dev.yml up -d postgres redis
python -m alembic upgrade head
python scripts/seed.py --interval 1800  # 20 个商品 + 计划
python scripts/dev.py up                # mock-shop + api + scheduler + reaper + worker
```

打开 <http://127.0.0.1:8000/docs>，默认账号 `admin / admin123`。

## Kubernetes（k3d 1+2）

```powershell
.\tools\k3d.exe cluster create price --servers 1 --agents 2 --api-port 6550 `
  -p "8080:80@loadbalancer" -p "8443:443@loadbalancer" `
  --volume "$PWD\deploy\k3d\registries.yaml:/etc/rancher/k3s/registries.yaml" --wait

docker build -f docker/Dockerfile --target api    -t price/api:v1 .
docker build -f docker/Dockerfile --target worker -t price/worker:v1 .
docker build -t price/web:v1 frontend
docker build -t price/mock-shop:v1 -f mock-shop/Dockerfile .

k3d image import -c price price/api:v1 price/worker:v1 price/web:v1 price/mock-shop:v1
kubectl apply -k deploy/base
kubectl apply -k deploy/observability
```

完整步骤与踩坑记录见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## 测试

```powershell
pytest tests/unit -q           # 36 个用例
pytest -m integration -q       # 需要 PG/Redis（dev compose）
```

## 脚本

| 脚本 | 用途 |
|---|---|
| `scripts/seed.py` | 建站点源 + 商品 + 计划 |
| `scripts/seed_demo.py` | 回填 3824/5456 演示数据集 |
| `scripts/loadtest.py` | 按速率灌任务，观察队列与扩缩容 |
| `scripts/verify_numbers.sql` | 数据集核对 SQL |
| `scripts/dev.py` | 本地开发栈启停 |

## 文档

- 设计文档（详细）：`docs/project2/design.md`（另见上级目录 `docs/` 下的方案稿）
- 部署手册：[docs/DEPLOY.md](docs/DEPLOY.md)
- 演示脚本：[docs/DEMO.md](docs/DEMO.md)
- 实施进度：[docs/STATUS.md](docs/STATUS.md)
- 压测与故障注入：[docs/perf/loadtest.md](docs/perf/loadtest.md)
