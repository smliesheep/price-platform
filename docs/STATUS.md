# 实施进度（2026-11-25 更新）

## 总览

| 目标 | 状态 | 证据 |
|---|---|---|
| 代码骨架（scheduler/worker/reaper/api/mock-shop/Vue） | ✅ | 40+ 后端文件、45 个前端文件 |
| Docker 镜像 | ✅ 4/4 | api / worker（Playwright 1.11GB）/ web / mock-shop 均已构建并导入集群 |
| k3d 1 server + 2 agents | ✅ | `kubectl get nodes`：1 control-plane + 2 worker，containerd |
| 业务栈部署 | ✅ | postgres / redis / api×2 / web×2 / worker(Playwright) / scheduler / reaper / mock-shop 全部 Running |
| Prometheus + Grafana | ✅ | 6 个抓取目标全部 up；Grafana 预置"Price Platform · 总览"看板 |
| EFK 日志 | ✅ | Fluent Bit DaemonSet → ES 单节点 → Kibana；`price-logs-2026.11.25` 已有 3000+ 文档，索引模式 `price-logs-*` 已建 |
| 告警 | ✅ | 5 条 Prometheus 规则 + Alertmanager → API webhook → `alerts` 表；手工告警已落库 |
| KEDA 弹性 | ✅ | ScaledObject READY/ACTIVE；HPA 随 lag 从 1 → 5 → 1 扩缩（`lagCount` 触发） |
| 单元测试 | ✅ | 36 passed |
| 集成测试 | ✅ | 4 passed（调度投递、抢占互斥、价格唯一键、消息往返） |
| 故障注入 | ✅ | 70% 5xx → retry_wait/failed/DLQ；孤儿 run 22s 内被 reaper 转为 retry_wait |
| 3824 / 5456 数据集 | ✅ | 回填后 `worker-demo-01` = 5456 条，`demo-4d` 价格 = 3824 条，not_found = 16 |
| 压测 | ✅ 初版 | `scripts/loadtest.py`：300 任务 4.25/s 投递，全部 success；200 任务可制造 ~200 lag |

## 关键验证记录

### 1. 集群基础栈

```
kubectl -n price get pods
api ×2 Running   web ×2 Running   worker ×N Running
postgres Running  redis Running   mock-shop Running
scheduler Running  reaper Running
```

入口 `http://127.0.0.1:8080`，登录 / 商品 / 概览 / 执行记录 / 告警接口均通过 Ingress 验证。

### 2. 观测栈

```
prometheus targets: api up, worker up×2, scheduler up, reaper up, prometheus up
ES: price-logs-2026.11.25 doc_count > 3000
kibana: index-pattern price-logs-* 已创建
alertmanager: POST /api/v2/alerts → API /alerts/webhook → alerts 表 1 行
```

### 3. KEDA

```
kubectl -n price get hpa keda-hpa-worker
lag 196（8s 延迟注入 + 200 任务突发）→ REPLICAS 5
lag 0 → REPLICAS 1（cooldown 120s）
```

> 注意：`redis-streams` 触发器用的是 `lagCount` / `activationLagCount`，不是 `lagThreshold`；写错回退成默认 `pendingEntriesCount`，HPA 目标会变成 5 且不随积压变化。

### 4. 故障注入

| 场景 | 结果 |
|---|---|
| mock 70% 5xx，8 次手动触发 | 9 条 retry_wait、4 条 failed（进 DLQ）、4 条 success |
| 伪造 20 分钟前的 running 记录 | reaper 22s 内改为 `retry_wait + timeout/orphaned`，指标 `price_reaper_reaped_total` +1 |
| 负载突发 | 队列 lag 200+，KEDA 扩到 5 副本，排空后回落 1 |

### 5. 数据集核对

```sql
SELECT count(*) FROM task_runs WHERE worker_id='worker-demo-01';        -- 5456
SELECT count(*) FROM price_records WHERE raw->>'source'='demo-4d';      -- 3824
```

### 5. 集群内 Playwright Worker

```powershell
kubectl -n price logs deploy/worker | Select-String browser_started
# event=browser_started version=159.0.8154.6
kubectl -n price exec postgres-0 -- psql -U price -d price -c `
  "select id, raw->>'page_title' from price_records order by id desc limit 3;"
# Mock 降噪耳塞 - Mock 商城（说明走的是浏览器渲染后的页面）
```

单任务耗时约 380–420ms（浏览器）vs 10–20ms（HTTP 适配器），日志 `duration_ms` 可直接对比。

## 已解决的阻塞

| 项 | 过程 | 结果 |
|---|---|---|
| Playwright 基础镜像 1.6GB | MCR 直连多次超时；最终在后台长时间拉取后完成 | `price/worker:v1` 1.11GB，已导入两个 agent 节点 |
| KEDA 镜像（ghcr.io） | Docker Hub 无此镜像、ghcr 直连超时 | 用 `ghcr.m.daocloud.io` 镜像前缀拉取后重新打 tag，导入 containerd |
| ES/Kibana 镜像（docker.elastic.co） | 拉取慢 | 复用本机已有的 7.17.3 镜像，`docker save` + `ctr import` 写入节点 |
| local-path provisioner 拉取失败 | 镜像拉取超时导致 PVC Pending | 改用 hostPath 静态 PV（`deploy/base/pv.yaml`） |

## 后续可选

1. 截图归档：Grafana 看板、Kibana 检索、KEDA 扩缩
2. 10000 任务压测报告（当前为 1000 任务）
3. 真实站点适配器（默认关闭，遵守 robots）

## 常用命令

```powershell
python scripts/dev.py up|down|status          # 本地栈
kubectl -n price get pods                     # 集群
kubectl -n price logs deploy/worker -f
kubectl -n observability port-forward svc/grafana 3000:3000
kubectl -n observability port-forward svc/kibana 5601:5601
```

