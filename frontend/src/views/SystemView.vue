<template>
  <div class="page">
    <div class="page-head">
      <div class="page-head__title">
        <h2>系统状态</h2>
        <p>Worker 心跳、Redis Stream 队列与版本信息 · 每 10 秒自动刷新</p>
      </div>
      <div class="page-head__actions">
        <el-button :icon="Refresh" :loading="refreshing" @click="refreshAll">刷新</el-button>
      </div>
    </div>

    <div class="stat-grid">
      <StatCard
        label="在线 Worker"
        :value="workersOnline"
        unit="台"
        :hint="`累计心跳 ${workers.length} 台`"
        :icon="Cpu"
        tone="success"
        :loading="workersLoading && workers.length === 0"
      />
      <StatCard
        label="队列长度"
        :value="queue ? formatNumber(queue.length) : '—'"
        hint="Stream 中待消费消息数"
        :icon="Odometer"
        tone="primary"
        :loading="queueLoading && !queue"
      />
      <StatCard
        label="队列 lag"
        :value="queue ? formatNumber(queue.lag) : '—'"
        :hint="queue ? `pending ${queue.pending} · DLQ ${queue.dlq}` : '加载中…'"
        :icon="Connection"
        :tone="queue && queue.lag > 0 ? 'warning' : 'primary'"
        :loading="queueLoading && !queue"
      />
      <StatCard
        label="服务版本"
        :value="version?.version ?? '—'"
        :hint="version ? `调度 tick ${version.scheduler_tick_sec}s` : '加载中…'"
        :icon="Monitor"
        tone="primary"
        :loading="versionLoading && !version"
      />
    </div>

    <section class="panel">
      <div class="panel-head">
        <div>
          <div class="panel-title">
            <el-icon><Cpu /></el-icon>
            Worker 心跳
          </div>
          <div class="panel-subtitle">在线状态依据最近一次心跳时间判断</div>
        </div>
        <el-tag size="small" type="success" effect="plain">{{ workersOnline }} 台在线</el-tag>
      </div>

      <div class="panel-body panel-body--flush">
        <ErrorBanner
          v-if="workersError"
          title="Worker 列表加载失败"
          :message="workersError"
          @retry="loadWorkers(true, false)"
        />
        <el-table v-loading="workersLoading" :data="workers" style="width: 100%">
          <el-table-column label="Worker ID" min-width="190" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono">{{ row.id }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="row.online ? 'success' : 'info'" size="small" effect="light">
                {{ row.online ? '在线' : '离线' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="节点" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">{{ row.node || '—' }}</template>
          </el-table-column>
          <el-table-column label="版本" width="100">
            <template #default="{ row }">{{ row.version || '—' }}</template>
          </el-table-column>
          <el-table-column label="处理中" width="90" align="center">
            <template #default="{ row }">
              <span class="nums">{{ row.inflight }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最近心跳" width="170">
            <template #default="{ row }">
              <span class="muted">{{ formatDateTime(row.last_heartbeat) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="心跳年龄" width="120">
            <template #default="{ row }">
              <span :class="row.online ? 'text-success' : 'text-danger'">
                {{ formatAge(row.heartbeat_age_sec) }}
              </span>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty
              v-if="!workersLoading && !workersError"
              :image-size="76"
              description="暂无 Worker 心跳数据"
            />
            <span v-else-if="!workersLoading" class="muted">暂无数据</span>
          </template>
        </el-table>
      </div>
    </section>

    <div class="overview-grid">
      <section class="panel">
        <div class="panel-head">
          <div>
            <div class="panel-title">
              <el-icon><Odometer /></el-icon>
              Redis Stream 队列
            </div>
            <div class="panel-subtitle">
              {{ queue ? `${queue.stream} / ${queue.group}` : '正在读取队列状态' }}
            </div>
          </div>
          <el-tag v-if="queue" size="small" type="info" effect="plain">
            consumers {{ queue.consumers.length }}
          </el-tag>
        </div>
        <div class="panel-body">
          <ErrorBanner
            v-if="queueError"
            title="队列状态加载失败"
            :message="queueError"
            @retry="loadQueue(true, false)"
          />
          <el-skeleton v-if="queueLoading && !queue" :rows="4" animated />
          <QueueGauge
            v-else-if="queue"
            :queue="queue"
            :group="queue.group"
            :loading="queueLoading && !queue"
          />
          <el-empty
            v-else-if="!queueLoading"
            :image-size="64"
            description="暂无队列数据"
          />
        </div>

        <div class="panel-head panel-head--plain">
          <div class="panel-title">
            <el-icon><Tickets /></el-icon>
            消费者
          </div>
        </div>
        <div class="panel-body panel-body--flush">
          <el-table
            v-loading="queueLoading"
            :data="queue?.consumers ?? []"
            size="small"
            style="width: 100%"
          >
            <el-table-column label="消费者" min-width="150" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="mono">{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column label="Pending" width="100" align="center">
              <template #default="{ row }">{{ row.pending }}</template>
            </el-table-column>
            <el-table-column label="空闲" width="120">
              <template #default="{ row }">{{ formatDuration(row.idle_ms) }}</template>
            </el-table-column>
            <template #empty>
              <el-empty
                v-if="!queueLoading && !queueError"
                :image-size="60"
                description="当前没有活跃消费者"
              />
            </template>
          </el-table>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <div class="panel-title">
              <el-icon><Monitor /></el-icon>
              版本信息
            </div>
            <div class="panel-subtitle">服务与调度器运行参数</div>
          </div>
        </div>
        <div class="panel-body">
          <ErrorBanner
            v-if="versionError"
            title="版本信息加载失败"
            :message="versionError"
            @retry="loadVersion(true, false)"
          />
          <el-skeleton v-if="versionLoading && !version" :rows="5" animated />
          <template v-else-if="version">
            <div class="info-list">
              <div class="info-row">
                <span class="info-row__label">服务版本</span>
                <span class="info-row__value mono">{{ version.version }}</span>
              </div>
              <div class="info-row">
                <span class="info-row__label">Queue Stream</span>
                <span class="info-row__value mono">{{ version.stream }}</span>
              </div>
              <div class="info-row">
                <span class="info-row__label">消费组</span>
                <span class="info-row__value mono">{{ version.group }}</span>
              </div>
              <div class="info-row">
                <span class="info-row__label">调度器 tick</span>
                <span class="info-row__value">{{ version.scheduler_tick_sec }} 秒</span>
              </div>
              <div class="info-row">
                <span class="info-row__label">重试延迟</span>
                <span class="info-row__value">{{ version.retry_delay_sec }} 秒</span>
              </div>
              <div class="info-row">
                <span class="info-row__label">Worker 并发</span>
                <span class="info-row__value">{{ version.worker_concurrency }}</span>
              </div>
            </div>
            <div class="hint-card mt-16">
              队列长度来自 Redis Stream XLEN，lag 表示消费组未确认消息数；DLQ 为超过最大重试后进入的死信队列。
            </div>
          </template>
          <el-empty
            v-else-if="!versionLoading && !versionError"
            :image-size="66"
            description="暂无版本信息"
          />
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Connection,
  Cpu,
  Monitor,
  Odometer,
  Refresh,
  Tickets,
} from '@element-plus/icons-vue'
import { onMounted, ref } from 'vue'

import { getQueue, getVersion, getWorkers } from '@/api/system'
import type { QueueInfo, VersionInfo, WorkerInfo } from '@/api/types'
import ErrorBanner from '@/components/ErrorBanner.vue'
import QueueGauge from '@/components/QueueGauge.vue'
import StatCard from '@/components/StatCard.vue'
import { usePolling } from '@/composables/usePolling'
import {
  errorMessage,
  formatAge,
  formatDateTime,
  formatDuration,
  formatNumber,
} from '@/utils/format'

const workers = ref<WorkerInfo[]>([])
const workersOnline = ref(0)
const workersLoading = ref(true)
const workersError = ref('')

const queue = ref<QueueInfo | null>(null)
const queueLoading = ref(true)
const queueError = ref('')

const version = ref<VersionInfo | null>(null)
const versionLoading = ref(true)
const versionError = ref('')

const refreshing = ref(false)

async function loadWorkers(initial = false, silent = true): Promise<void> {
  if (initial) workersLoading.value = true
  try {
    const result = await getWorkers({ silent })
    workers.value = result.items
    workersOnline.value = result.online
    workersError.value = ''
  } catch (err) {
    workersError.value = errorMessage(err, 'Worker 列表加载失败')
  } finally {
    workersLoading.value = false
  }
}

async function loadQueue(initial = false, silent = true): Promise<void> {
  if (initial) queueLoading.value = true
  try {
    queue.value = await getQueue({ silent })
    queueError.value = ''
  } catch (err) {
    queueError.value = errorMessage(err, '队列状态加载失败')
  } finally {
    queueLoading.value = false
  }
}

async function loadVersion(initial = false, silent = true): Promise<void> {
  if (initial) versionLoading.value = true
  try {
    version.value = await getVersion({ silent })
    versionError.value = ''
  } catch (err) {
    versionError.value = errorMessage(err, '版本信息加载失败')
  } finally {
    versionLoading.value = false
  }
}

async function refreshAll(): Promise<void> {
  refreshing.value = true
  try {
    await Promise.allSettled([
      loadWorkers(false, false),
      loadQueue(false, false),
      loadVersion(false, false),
    ])
  } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  void loadWorkers(true, false)
  void loadQueue(true, false)
  void loadVersion(true, false)
})

usePolling(() => {
  void loadWorkers(false, true)
  void loadQueue(false, true)
  void loadVersion(false, true)
}, 10_000)
</script>
