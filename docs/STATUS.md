# 实施进度（2026-11-25）

## 已完成

### 代码

| 模块 | 状态 | 说明 |
|---|---|---|
| `src/price_platform/common/` | ✅ | settings / db / queue / logging / metrics / errors / timeutil / security |
| `src/price_platform/models/` | ✅ | 7 张表 SQLAlchemy 映射 |
| `alembic/` | ✅ | 0001_init 迁移，已在本地与集群执行成功 |
| `scheduler/` | ✅ | 30s tick + SKIP LOCKED + 1s 延时重试提升 + advisory lock 选主 |
| `worker/` | ✅ | 消费组、claim、Playwright 采集、失败分类、ZSET 重试、DLQ、心跳 |
| `reaper/` | ✅ | 孤儿回收、丢消息补投、僵尸 retry_wait 修复、队列指标 |
| `api/` | ✅ | 27+ 端点（商品/任务/记录/概览/Worker/队列/告警 webhook），JWT |
| `mock-shop/` | ✅ | 20 商品、价格波动、5xx/超时/404 注入、admin 接口 |
| `frontend/` | ✅ | Vue3 + TS + Element Plus + ECharts，7 个页面，构建通过（2.55MB） |
| `tests/unit/` | ✅ | 36 个用例全绿（时间槽、错误分类、消息契约、解析器） |

### 本地闭环（已验证）

20 个商品 → 调度投递 → Worker 用 Playwright 抓取 → 价格入库：`price_records=20`，`success=20`，attempt 全为 1；手动触发、重试、DLQ 路径均已跑通。

### 集群

- k3d：1 server + 2 agents，containerd 2.2.3，控制面已打 taint
- 已部署：postgres / redis / api ×2 / web ×2 / scheduler / reaper / mock-shop / migrate Job
- 入口：<http://127.0.0.1:8080>（web）+ `/api/v1/*`（api），登录与商品列表验证通过
- 数据：20 个商品 + 计划（60s 间隔，便于演示）

### 部署资产

- `deploy/base/`：namespace、configmap、secret、PV/PVC、postgres、redis、mock-shop、api、scheduler、worker、reaper、web、ingress、PDB、NetworkPolicy、migrate Job、cleanup CronJob
- `deploy/observability/`：Prometheus + 5 条告警规则、Alertmanager（webhook → API 落库）、Grafana 看板、EFK（Fluent Bit / ES / Kibana）
- `deploy/keda/scaledobject.yaml`
- `deploy/k3d/registries.yaml`（containerd 镜像加速）
- `docs/DEPLOY.md`：从零搭建步骤与已知坑

## 进行中 / 阻塞

| 项 | 状态 | 说明 |
|---|---|---|
| worker 镜像 | 🔄 | 官方 Playwright 基础镜像 1.6GB，MCR 下载极慢，已后台拉取 |
| 观测栈部署 | ⏳ | manifests 已写完，等 worker + 镜像拉取完成 |
| KEDA | ⏳ | ScaledObject 已写，待安装 KEDA operator |
| 演示数据集 3824/5456 | ⏳ | 需要先有稳定运行的 Worker |
| 压测脚本 | ⏳ | `scripts/loadtest.py` 待写 |
| 集成测试 | ⏳ | `tests/integration` 待写（依赖集群或 compose） |

## 下一步

1. 完成 worker 镜像（MCR 拉取完成后 `docker build --target worker` + `k3d image import` + 扩到 2 副本）
2. 部署 observability 栈，验证 Grafana 看板与 Kibana 日志
3. 安装 KEDA，灌任务演示 2 → N 扩容
4. 生成 `demo-4d` 数据集并核对 3824/5456
5. 压测 + 故障注入（删 Pod、注入 5xx、Redis 重启）
6. 补齐 README、答辩材料、截图

## 常用命令

```powershell
# 本地开发栈
python scripts/dev.py up / down / status

# 集群
kubectl -n price get pods
kubectl -n price logs deploy/worker -f
k3d image import -c price price/worker:v1
kubectl -n price rollout restart deploy/worker
```
