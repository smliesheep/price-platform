<template>
  <div class="page">
    <div class="page-head">
      <div class="page-head__title">
        <h2>执行记录</h2>
        <p>检索采集执行结果，点击任意行查看完整字段与错误信息</p>
      </div>
      <div class="page-head__actions">
        <el-button :icon="Refresh" :loading="loading" @click="load(true, false)">刷新</el-button>
      </div>
    </div>

    <div class="filter-bar">
      <div class="filter-item">
        <span class="filter-item__label">状态</span>
        <el-select v-model="filters.status" placeholder="全部状态">
          <el-option label="全部状态" value="" />
          <el-option
            v-for="option in statusOptions"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </div>
      <div class="filter-item">
        <span class="filter-item__label">错误类型</span>
        <el-input
          v-model="filters.error_type"
          placeholder="如 timeout / parse_error"
          clearable
          @keyup.enter="handleSearch"
        />
      </div>
      <div class="filter-item">
        <span class="filter-item__label">Worker</span>
        <el-input
          v-model="filters.worker_id"
          placeholder="Worker ID"
          clearable
          @keyup.enter="handleSearch"
        />
      </div>
      <div class="filter-item">
        <span class="filter-item__label">商品 ID</span>
        <el-input-number
          v-model="filters.product_id"
          :min="1"
          :controls="false"
          placeholder="全部商品"
          style="width: 130px"
        />
      </div>
      <div class="filter-item filter-datetime">
        <span class="filter-item__label">时间范围</span>
        <el-date-picker
          v-model="filters.timeRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          :default-time="defaultTime"
          clearable
        />
      </div>
      <div class="filter-actions">
        <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
        <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
      </div>
    </div>

    <ErrorBanner
      v-if="error"
      title="执行记录加载失败"
      :message="error"
      @retry="load(true, false)"
    />

    <section class="panel">
      <div class="panel-body panel-body--flush">
        <el-table
          v-loading="loading"
          :data="rows"
          :row-class-name="rowClassName"
          style="width: 100%"
          @row-click="openRun"
        >
          <el-table-column label="ID" width="84">
            <template #default="{ row }">
              <span class="mono">#{{ row.id }}</span>
            </template>
          </el-table-column>
          <el-table-column label="商品" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="table-title">{{ row.product_title || `商品 #${row.product_id}` }}</div>
              <div class="table-sub">商品 #{{ row.product_id }} · 任务 #{{ row.task_id }}</div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="94">
            <template #default="{ row }">
              <StatusTag :status="row.status" />
            </template>
          </el-table-column>
          <el-table-column label="尝试" width="72" align="center">
            <template #default="{ row }">第 {{ row.attempt }} 次</template>
          </el-table-column>
          <el-table-column label="Worker" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">{{ row.worker_id || '—' }}</template>
          </el-table-column>
          <el-table-column label="排队时间" width="168">
            <template #default="{ row }">
              <span class="muted">{{ formatDateTime(row.queued_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="耗时" width="96">
            <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
          </el-table-column>
          <el-table-column label="HTTP" width="78" align="center">
            <template #default="{ row }">
              <span :class="httpClass(row.http_status)">{{ row.http_status ?? '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="错误类型" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">
              <span class="mono" :class="row.error_type ? 'text-danger' : 'muted'">
                {{ row.error_type || '—' }}
              </span>
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
              v-if="!loading && !error"
              :image-size="80"
              description="暂无执行记录，试试调整筛选条件"
            />
            <span v-else-if="!loading" class="muted">暂无数据</span>
          </template>
        </el-table>

        <div v-if="total > 0" class="table-footer">
          <span class="table-footer__total">共 {{ total }} 条执行记录</span>
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50, 100]"
            layout="sizes, prev, pager, next, jumper"
            background
            @current-change="handlePageChange"
            @size-change="handleSizeChange"
          />
        </div>
      </div>
    </section>

    <RunDrawer v-model="drawerVisible" :run-id="selectedRunId" />
  </div>
</template>

<script setup lang="ts">
import { Refresh, RefreshLeft, Search } from '@element-plus/icons-vue'
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getRuns } from '@/api/runs'
import type { Run, RunQuery } from '@/api/types'
import ErrorBanner from '@/components/ErrorBanner.vue'
import RunDrawer from '@/components/RunDrawer.vue'
import StatusTag from '@/components/StatusTag.vue'
import { errorMessage, formatDateTime, formatDuration } from '@/utils/format'

const route = useRoute()
const router = useRouter()

const statusOptions = [
  { value: 'queued', label: '排队中' },
  { value: 'running', label: '执行中' },
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'timeout', label: '超时' },
  { value: 'canceled', label: '已取消' },
  { value: 'retry_wait', label: '等待重试' },
]

const filters = reactive({
  status: '',
  error_type: '',
  worker_id: '',
  product_id: undefined as number | undefined,
  timeRange: null as Date[] | null,
})

const defaultTime: [Date, Date] = [
  new Date(2000, 1, 1, 0, 0, 0),
  new Date(2000, 1, 1, 23, 59, 59),
]

const rows = ref<Run[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(true)
const error = ref('')

const drawerVisible = ref(false)
const selectedRunId = ref<number | null>(null)

function rowClassName(): string {
  return 'is-clickable'
}

function buildQuery(): RunQuery {
  return {
    status: filters.status || undefined,
    error_type: filters.error_type.trim() || undefined,
    worker_id: filters.worker_id.trim() || undefined,
    product_id: filters.product_id,
    from: filters.timeRange?.[0]?.toISOString(),
    to: filters.timeRange?.[1]?.toISOString(),
    page: page.value,
    page_size: pageSize.value,
  }
}

async function load(initial = false, silent = true): Promise<void> {
  if (initial) loading.value = true
  try {
    const result = await getRuns(buildQuery(), { silent })
    rows.value = result.items
    total.value = result.total
    page.value = result.page
    pageSize.value = result.page_size
    error.value = ''
  } catch (err) {
    error.value = errorMessage(err, '执行记录加载失败')
  } finally {
    loading.value = false
  }
}

function handleSearch(): void {
  page.value = 1
  void load(true, false)
}

function handleReset(): void {
  filters.status = ''
  filters.error_type = ''
  filters.worker_id = ''
  filters.product_id = undefined
  filters.timeRange = null
  page.value = 1
  if (route.query.status) void router.replace({ path: '/runs' })
  void load(true, false)
}

function handlePageChange(value: number): void {
  page.value = value
  void load(true, false)
}

function handleSizeChange(value: number): void {
  pageSize.value = value
  page.value = 1
  void load(true, false)
}

function httpClass(status: number | null): string {
  if (status === null) return 'muted'
  if (status >= 200 && status < 300) return 'text-success'
  if (status >= 500) return 'text-danger'
  if (status >= 400) return 'text-warning'
  return ''
}

function openRun(row: Run): void {
  selectedRunId.value = row.id
  drawerVisible.value = true
}

onMounted(() => {
  const queryStatus = route.query.status
  if (
    typeof queryStatus === 'string' &&
    statusOptions.some((option) => option.value === queryStatus)
  ) {
    filters.status = queryStatus
  }
  void load(true, false)
})
</script>
