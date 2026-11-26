# 部署手册（k3d 1 server + 2 agents）

> 目标：在一台 Windows 机器上复现"1 控制节点 + 2 工作节点"的集群，并跑起全部组件。

## 0. 前置

| 组件 | 版本 | 说明 |
|---|---|---|
| Docker Desktop | 29.x | WSL2 后端，内存至少 11GB（`.wslconfig` 里 `memory=11GB`） |
| k3d | v5.9.0 | `winget install k3d` 或从 releases 下载后放进 `tools/` |
| kubectl | 随 Docker Desktop | 或单独安装 |
| Python | 3.10+ | 本地开发/测试 |

### 0.1 镜像加速（国内网络必需）

Docker Hub 无法直连时，给 Docker Desktop 配 registry mirror（`%USERPROFILE%\.docker\daemon.json`）：

```json
{
  "registry-mirrors": ["https://docker.1panel.live", "https://docker.m.daocloud.io"]
}
```

k3d 节点内的 containerd 需要单独配置（`deploy/k3d/registries.yaml`）：

```yaml
mirrors:
  docker.io:
    endpoint:
      - "https://docker.m.daocloud.io"
      - "https://docker.1panel.live"
```

## 1. 创建集群

```powershell
k3d cluster create price --servers 1 --agents 2 --api-port 6550 `
  -p "8080:80@loadbalancer" -p "8443:443@loadbalancer" `
  --volume "$PWD\deploy\k3d\registries.yaml:/etc/rancher/k3s/registries.yaml" `
  --wait

# k3d 生成的 kubeconfig 用的是 host.docker.internal，Windows 上改成 127.0.0.1
(Get-Content "$env:USERPROFILE\.kube\config" -Raw) -replace 'host\.docker\.internal:6550','127.0.0.1:6550' |
  Set-Content "$env:USERPROFILE\.kube\config"
kubectl config use-context k3d-price

# 控制面不跑业务
kubectl taint nodes k3d-price-server-0 node-role.kubernetes.io/control-plane=:NoSchedule --overwrite
```

## 2. 构建并导入镜像

```powershell
docker build -f docker/Dockerfile --target api    -t price/api:v1 .
docker build -f docker/Dockerfile --target worker -t price/worker:v1 .
docker build -t price/web:v1 frontend
docker build -t price/mock-shop:v1 -f mock-shop/Dockerfile .

k3d image import -c price price/api:v1 price/worker:v1 price/web:v1 price/mock-shop:v1
```

## 3. 部署业务栈

```powershell
kubectl apply -k deploy/base
kubectl -n price wait --for=condition=ready pod/postgres-0 --timeout=180s

# 数据库迁移（每次发布前）
kubectl -n price delete job migrate --ignore-not-found
kubectl apply -f deploy/base/migrate-job.yaml
kubectl -n price wait --for=condition=complete job/migrate --timeout=120s
```

### 3.1 灌入演示数据

```powershell
kubectl -n price port-forward svc/postgres 15432:5432
kubectl -n price port-forward svc/mock-shop 18088:8080
# 另开终端
$env:PP_DATABASE_URL = "postgresql://price:price@127.0.0.1:15432/price"
python scripts/seed.py --interval 1800 --mock-url http://127.0.0.1:18088 --source-base-url http://mock-shop:8080
```

## 4. 访问

| 入口 | 地址 | 说明 |
|---|---|---|
| Web | <http://127.0.0.1:8080> | 由 `price-any-host` Ingress 兜底路由 |
| API 文档 | <http://127.0.0.1:8080/api/v1/...> | 或 `kubectl -n price port-forward svc/api 8000:8000` 后访问 `/docs` |
| Grafana | `kubectl -n observability port-forward svc/grafana 3000:3000` | admin/admin |
| Kibana | `kubectl -n observability port-forward svc/kibana 5601:5601` | — |

默认账号：`admin / admin123`。

## 5. 可观测栈

```powershell
kubectl apply -k deploy/observability
```

包含：Prometheus（7 天保留、5 条告警规则）、Alertmanager（webhook 到 API 落库）、Grafana（预置总览看板）、EFK（Fluent Bit → Elasticsearch 单节点 → Kibana）。

## 6. KEDA 弹性

```powershell
kubectl apply -f https://github.com/kedacore/keda/releases/download/v2.16.0/keda-2.16.0.yaml
kubectl apply -f deploy/keda/scaledobject.yaml
kubectl -n price get scaledobject,hpa
```

## 7. 已知环境问题

| 问题 | 原因 | 处理 |
|---|---|---|
| Pod 卡在 `ContainerCreating`，事件里 `rancher/mirrored-pause` 拉取失败 | 节点 containerd 没走 mirror | 重建集群时挂 `registries.yaml`，或重启节点容器 |
| PVC `Pending` | local-path provisioner 镜像拉取慢 | 已改用 `deploy/base/pv.yaml` 的 hostPath 静态 PV |
| Worker 镜像 1.6GB 拉取慢 | Playwright 基础镜像 | 提前 `docker pull` 并 `k3d image import`，或改用 slim + 系统 Chromium |
| 8080 被占用 | 本地已有服务 | 改 k3d 端口映射，或 `kubectl port-forward` |


