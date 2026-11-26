# 演示脚本（15 分钟）

前置：
```powershell
kubectl get nodes                     # 1 server + 2 agents
kubectl -n price get pods             # 业务栈全绿
kubectl -n observability get pods     # Prometheus / Grafana / EFK 全绿
kubectl -n keda get pods              # KEDA 三件套
```

## 1. 集群与部署（2 分钟）

```powershell
kubectl get nodes -o wide
kubectl -n price get pods -o wide
kubectl -n price get deploy
```

讲解点：k3d 起 1 控制面 + 2 工作节点，containerd 运行时；控制面打了 `NoSchedule`，业务只跑在 agent 上；PG/Redis 用 hostPath 静态 PV（资源受限下的取舍）。

## 2. 架构与数据流（2 分钟）

打开设计文档的架构图（`docs/project2/design.md`），讲三条链路：

1. scheduler 30s 扫描 `next_run_at`，`FOR UPDATE SKIP LOCKED` 锁行 → 写 `task_runs(queued)` → XADD；
2. Worker 消费组抢占（条件 UPDATE）→ Playwright/HTTP 适配器抓取 → 事务写价格 + 读模型；
3. 失败进 ZSET 5s 后重试；3 次仍失败进 DLQ；reaper 兜底孤儿任务。

## 3. 现场采集（3 分钟）

```powershell
# 手动触发一个商品
$login = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/v1/auth/login `
  -ContentType application/json -Body '{"username":"admin","password":"admin123"}'
$h = @{ Authorization = "Bearer $($login.data.access_token)" }
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/v1/products/1/run -Headers $h

# 看执行记录
Invoke-RestMethod -Uri "http://127.0.0.1:8080/api/v1/runs?page_size=3" -Headers $h |
  ConvertTo-Json -Depth 4
```

浏览器打开 <http://127.0.0.1:8080>：
- 概览：24h 采集量、成功率、队列 lag、Top 错误
- 商品详情：价格曲线（24h/7d/30d、raw/1h/1d、目标价线）
- 执行记录：抽屉里看 trace_id / 错误 / Worker Pod

## 4. 故障与重试（3 分钟）

```powershell
# 70% 失败注入
curl -X POST http://127.0.0.1:18088/admin/config -H "Content-Type: application/json" -d '{"fail_rate":0.7}'
1..8 | ForEach-Object { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/v1/products/$_/run" -Headers $h }
Start-Sleep 20
kubectl -n price exec postgres-0 -- psql -U price -d price -c `
  "select status,error_type,count(*) from task_runs where queued_at > now()-interval '2 minutes' group by 1,2;"
kubectl -n price exec redis-77c4bbbcd6-tznpz -- redis-cli XLEN price:tasks:dlq
```

预期：`retry_wait / http_5xx` + `failed / http_5xx`，DLQ 增长。

```powershell
# 恢复
curl -X POST http://127.0.0.1:18088/admin/reset
```

## 5. 自愈（2 分钟）

```powershell
kubectl -n price exec postgres-0 -- psql -U price -d price -c "
INSERT INTO task_runs (task_id, product_id, slot_at, attempt, status, worker_id, started_at)
SELECT id, product_id, now() - interval '20 minutes', 1, 'running', 'ghost', now() - interval '20 minutes'
FROM tasks WHERE id = 1;"
Start-Sleep 20
kubectl -n price exec postgres-0 -- psql -U price -d price -c `
  "select status,error_type,error_msg from task_runs where worker_id='ghost';"
```

预期 20 秒内被 reaper 改成 `retry_wait / timeout / orphaned`。

## 6. 弹性（2 分钟）

```powershell
curl -X POST http://127.0.0.1:18088/admin/config -H "Content-Type: application/json" -d '{"delay_ms":8000}'
python scripts/loadtest.py --total 200 --rate 50
kubectl -n price get hpa keda-hpa-worker -w     # 1 → 5
kubectl -n price get pods -l app=worker -w
```

排空后 cooldown 120s 缩回 1。

## 7. 可观测（1 分钟）

```powershell
kubectl -n observability port-forward svc/grafana 3000:3000
kubectl -n observability port-forward svc/kibana 5601:5601
```

Grafana：成功率、吞吐、耗时 P95、队列水位、错误分布、重复消费率。
Kibana：索引 `price-logs-*`，搜索 `event: task_failed`、`error_type: parse`、按 `trace_id` 串联。

## 8. 数据口径（1 分钟）

```powershell
Get-Content scripts/verify_numbers.sql | kubectl -n price exec -i postgres-0 -- psql -U price -d price
```

预期：`demo_runs=5456`、`demo_prices=3824`、`demo_not_found=16`。

## 常见追问准备

见设计文档 §9.2 的 13 个问答（Redis Stream vs List、幂等三层、单副本调度、30s 精度、ZSET 重试、超时双保险、资源取舍、containerd、ES 单节点、数据口径、选择器失效、RPA 与爬虫区别、扩容路径）。


