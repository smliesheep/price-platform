<template>
  <div class="page">
    <div class="page-head">
      <div class="page-head__title">
        <h2>概览</h2>
        <p>近 24 小时采集表现与队列健康度 · 每 15 秒自动刷新</p>
      </div>
      <div class="page-head__actions">
        <span v-if="overview" class="muted nowrap">
          生成于 {{ formatDateTime(overview.generated_at) }}
        </span>
        <el-button :icon="Refresh" :loading="manualRefreshing" @click="refreshAll">刷新</el-button>
      </div>
    </div>

    <ErrorBanner
      v-if="overviewError"
      title="概览指标加载失败"
      :message="overviewError"
      @retry="refreshAll"
    />

    <div class="stat-grid">
      <StatCard
        label="24h 采集量"
        :value="overview ? formatNumber(overview.prices_24h) : '—'"
        :hint="overview ? `启用商品 ${overview.products_enabled} / 共 ${overview.products_total}` : '加载中…'"
        :icon="TrendCharts"
        tone="primary"
        :loading="loading && !overview"
      />
      <StatCard
        label="24h 成功率"
        :value="overview ? formatPercent(overview.success_rate) : '—'"
        :hint="overview ? `成功 ${formatNumber(overview.success_24h)} / 执行 ${formatNumber(overview.runs_24h)}` : '加载中…'"
        :icon="CircleCheck"
        tone="success"
        :loading="loading && !overview"
      />
      <StatCard
        label="在线 Worker"
        :value="overview ? overview.workers_online : '—'"
        :hint="overview ? `进行中任务 ${overview.inflight}` : '加载中…'"
        :icon="Cpu"
        tone="warning"
        :loading="loading && !overview"
      />
      <StatCard
        label="队列 lag"
        :value="overview ? formatNumber(overview.queue.lag) : '—'"
        :hint="overview ? `Stream 长度 ${formatNumber(overview.queue.length)} · DLQ ${overview.queue.dlq}` : '加载中…'"
        :icon="Odometer"
        :tone="overview && overview.queue.lag > 0 ? 'danger' : 'primary'"
        :loading="loading && !overview"
      />
    </div>

    <div class="overview-grid">
      <section class="panel">
        <div class="panel-head">
          <div>
            <div class="panel-title">
              <el-icon><Odometer /></el-icon>
              队列水位
            </div>
            <div class="panel-subtitle">Redis Stream 消费组积压情况</div>
          </div>
          <el-tag v-if="overview" size="small" type="info" effect="plain">
            lag {{ formatNumber(overview.queue.lag) }}
          </el-tag>
        </div>
        <div class="panel-body">
          <el-skeleton v-if="loading && !overview" :rows="3" animated />
          <QueueGauge v-else :queue="overview?.queue ?? null" />
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <div class="panel-title">
              <el-icon><Warning /></el-icon>
              Top 错误
            </div>
            <div class="panel-subtitle">近 24 小时失败 / 超时聚合</div>
          </div>
          <el-tag size="small" type="danger" effect="plain">{{ topErrors.length }} 类</el-tag>
        </div>
        <div class="panel-body">
          <el-skeleton v-if="loading && !overview" :rows="3" animated />
          <div v-else-if="topErrors.length > 0" class="error-list">
            <div v-for="item in topErrors" :key="item.error_type" class="error-item">
              <div class="error-item__head">
                <span class="error-item__name" :title="item.error_type">{{ item.error_type }}</span>
                <span class="error-item__count">{{ item.count }}</span>
              </div>
              <div class="error-item__bar">
                <div class="error-item__fill" :style="{ width: errorWidth(item.count) }" />
              </div>
            </div>
          </div>
          <el-empty v-else :image-size="64" description="24 小时内无失败记录" class="mini-empty" />
        </div>
      </section>
    </div>

    <section class="panel">
      <div class="panel-head">
        <div>
          <div class="panel-title">
            <el-icon><Warning /></el-icon>
            最近失败记录
          </div>
          <div class="panel-subtitle">点击任意行查看 trace_id、错误信息与耗时</div>
        </div>
        <div class="panel-actions">
          <el-button text type="primary" @click="goRuns">查看全部</el-button>
        </div>
      </div>

      <div class="panel-body panel-body--flush">
        <ErrorBanner
          v-if="runsError"
          title="失败记录加载失败"
          :message="runsError"
          class="mb-12"
          @retry="refreshAll"
        />

        <el-table
          v-loading="failedLoading"
          :data="failedRuns"
          :row-class-name="rowClassName"
          style="width: 100%"
          @row-click="openRun"
        >
          <el-table-column prop="id" label="ID" width="76">
            <template #default="{ row }">
              <span class="mono">#{{ row.id }}</span>
            </template>
          </el-table-column>
          <el-table-column label="商品" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="table-title">{{ row.product_title || `商品 #${row.product_id}` }}</div>
              <div class="table-sub">
                {{ row.product_id ? `商品 ID ${row.product_id}` : '—' }} · 第 {{ row.attempt }} 次尝试
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="92">
            <template #default="{ row }">
              <StatusTag :status="row.status" />
            </template>
          </el-table-column>
          <el-table-column label="错误类型" min-width="150" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono text-danger">{{ row.error_type || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Worker" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ row.worker_id || '—' }}</template>
          </el-table-column>
          <el-table-column label="耗时" width="100">
            <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
          </el-table-column>
          <el-table-column label="排队时间" width="168">
            <template #default="{ row }">
              <span class="muted">{{ formatDateTime(row.queued_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click.stop="openRun(row)">
                详情
              </el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty
              v-if="!failedLoading && !runsError"
              :image-size="74"
              description="最近没有失败记录，服务运行良好"
            />
            <span v-else-if="!failedLoading" class="muted">暂无数据</span>
          </template>
        </el-table>

        <div v-if="failedTotal > 0" class="table-footer">
          <span class="table-footer__total">共 {{ failedTotal }} 条失败记录</span>
          <el-button text type="primary" @click="goRuns">查看全部执行记录</el-button>
        </div>
      </div>
    </section>

    <RunDrawer v-model="drawerVisible" :run-id="selectedRunId" />
  </div>
</template>

<script setup lang="ts">
import {
  CircleCheck,
  Cpu,
  Odometer,
  Refresh,
  TrendCharts,
  Warning,
} from '@element-plus/icons-vue'
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getOverview } from '@/api/overview'
import { getRuns } from '@/api/runs'
import type { Overview, Run } from '@/api/types'
import ErrorBanner from '@/components/ErrorBanner.vue'
import QueueGauge from '@/components/QueueGauge.vue'
import RunDrawer from '@/components/RunDrawer.vue'
import StatCard from '@/components/StatCard.vue'
import StatusTag from '@/components/StatusTag.vue'
import { usePolling } from '@/composables/usePolling'
import {
  errorMessage,
  formatDateTime,
  formatDuration,
  formatNumber,
  formatPercent,
} from '@/utils/format'

const router = useRouter()

const overview = ref<Overview | null>(null)
const loading = ref(true)
const overviewError = ref('')

const failedRuns = ref<Run[]>([])
const failedTotal = ref(0)
const failedLoading = ref(true)
const runsError = ref('')

const manualRefreshing = ref(false)
const drawerVisible = ref(false)
const selectedRunId = ref<number | null>(null)

const topErrors = computed(() => overview.value?.top_errors ?? [])
const maxErrorCount = computed(() =>
  Math.max(1, ...topErrors.value.map((item) => item.count)),
)

function errorWidth(count: number): string {
  return `${Math.max(4, (count / maxErrorCount.value) * 100)}%`
}

function rowClassName(): string {
  return 'is-clickable'
}

async function loadOverview(initial = false, silent = true): Promise<void> {
  if (initial) loading.value = true
  try {
    overview.value = await getOverview({ silent })
    overviewError.value = ''
  } catch (error) {
    overviewError.value = errorMessage(error, '概览指标加载失败')
  } finally {
    loading.value = false
  }
}

async function loadFailedRuns(initial = false, silent = true): Promise<void> {
  if (initial) failedLoading.value = true
  try {
    const result = await getRuns(
      { status: 'failed', page: 1, page_size: 8 },
      { silent },
    )
    failedRuns.value = result.items
    failedTotal.value = result.total
    runsError.value = ''
  } catch (error) {
    runsError.value = errorMessage(error, '失败记录加载失败')
  } finally {
    failedLoading.value = false
  }
}

async function refreshAll(): Promise<void> {
  manualRefreshing.value = true
  try {
    await Promise.allSettled([
      loadOverview(false, false),
      loadFailedRuns(false, false),
    ])
  } finally {
    manualRefreshing.value = false
  }
}

function openRun(row: Run): void {
  selectedRunId.value = row.id
  drawerVisible.value = true
}

function goRuns(): void {
  void router.push({ path: '/runs', query: { status: 'failed' } })
}

onMounted(() => {
  void loadOverview(true, false)
  void loadFailedRuns(true, false)
})

usePolling(() => {
  void loadOverview(false, true)
  void loadFailedRuns(false, true)
}, 15_000)
</script>
