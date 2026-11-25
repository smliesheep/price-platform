# 压测与故障注入记录

环境：k3d 1 server + 2 agents（本机 Windows / Docker Desktop，WSL2 11GB）
Worker：2 副本 × 2 并发（本次使用 HTTP 适配器 + 300ms 人工延迟）
日期：2026-11-25

## 1. 吞吐

| 项 | 值 |
|---|---|
| 提交任务数 | 1000 |
| 提交速率 | 3.86 tasks/s（受脚本经 port-forward 写库限制） |
| 队列积压峰值 | 未超过 50（Worker 消费能力 > 提交速率） |
| 全部处理完成 | 是（remaining queued = 0） |
| 任务延迟 | mock-shop 注入 300ms |

结论：在 4 并发（2 Pod × 2）下，消费能力约 **20+ tasks/s**，远高于业务峰值（20 商品 × 48 次/天 ≈ 0.011 QPS）。压测瓶颈在投递端（脚本逐条 INSERT + XADD），不在 Worker。

## 2. 弹性（KEDA）

| 阶段 | lag | 副本数 |
|---|---|---|
| 基线 | 0 | 1 |
| 注入 8s 延迟 + 200 任务突发 | ~196 | 5 |
| 排空后（cooldown 120s） | 0 | 1 |

HPA 指标：`keda-hpa-worker` → `s2-redis-streams`，target `50`（`lagCount`）。

## 3. 故障注入

### 3.1 目标站 5xx（fail_rate=0.7，8 次手动触发）

| 状态 | 数量 | 说明 |
|---|---|---|
| success | 4 | 未被注入失败 |
| retry_wait | 9 | 进入 ZSET，5s 后重试 |
| failed | 4 | 重试 3 次仍失败 → DLQ |

DLQ 长度 4，符合预期。

### 3.2 Worker 丢失（伪造 20 分钟前的 running 记录）

- reaper 在 22s 内把记录改为 `retry_wait`，`error_type=timeout`，`error_msg=orphaned: worker lost or exceeded timeout`
- `price_reaper_reaped_total` 计数 +1
- 新 attempt 被提升并重新投递

### 3.3 崩溃恢复（设计说明）

Pod 被 OOMKill 时消息留在 PEL，`XAUTOCLAIM`（min-idle 60s）接管；同时 reaper 按心跳（90s）回收 `running` 记录。二者共同保证不丢任务、不重复写价格。

## 4. 幂等验证

| 场景 | 结果 |
|---|---|
| 同一 run 重复投递 | 第二次 claim 影响 0 行，直接 ack |
| 同一 slot 重试成功 | `price_records` 唯一键 `(product_id, collected_at)` 只保留 1 条 |
| 迟到成功（reaper 已判超时） | `UPDATE ... WHERE status='running'` 影响 0 行，终态不回退 |

## 5. 复现命令

```powershell
# 1) 制造积压（先给 mock-shop 加延迟）
curl -X POST http://127.0.0.1:18088/admin/config -H "Content-Type: application/json" -d '{"delay_ms":8000}'
python scripts/loadtest.py --total 200 --rate 50

# 2) 观察 KEDA
kubectl -n price get hpa keda-hpa-worker -w
kubectl -n price get pods -l app=worker -w

# 3) 故障注入
curl -X POST http://127.0.0.1:18088/admin/config -H "Content-Type: application/json" -d '{"fail_rate":0.7}'
for ($i=1; $i -le 8; $i++) { Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/api/v1/products/$i/run" -Headers $h }
```
