<template>
  <div class="page">
    <div class="page-head">
      <div class="page-head__title">
        <h2>商品详情</h2>
        <p>价格曲线、目标价与采集计划配置</p>
      </div>
      <div class="page-head__actions">
        <el-button :icon="Back" @click="goBack">返回列表</el-button>
        <el-button :icon="Refresh" :loading="refreshing" @click="refreshAll">刷新</el-button>
        <el-button
          type="primary"
          :icon="VideoPlay"
          :loading="running"
          :disabled="!product?.enabled || product?.task?.status !== 'active'"
          :title="product?.task?.status !== 'active' ? '采集计划已暂停，请先在下方恢复计划' : '立即采集'"
          @click="runNow"
        >
          立即采集
        </el-button>
      </div>
    </div>

    <ErrorBanner
      v-if="error"
      title="商品信息加载失败"
      :message="error"
      @retry="reload"
    />

    <section v-if="product" class="panel">
      <div class="panel-body">
        <div class="detail-head">
          <div class="detail-head__main">
            <div class="detail-title">
              <h2>{{ product.title }}</h2>
              <StatusTag :status="product.last_status" kind="product" />
              <el-tag size="small" type="info" effect="plain">{{ product.source_name || '未知来源' }}</el-tag>
              <el-tag v-if="!product.enabled" size="small" type="info" effect="plain">已停用</el-tag>
            </div>

            <div class="detail-meta">
              <span>商品 ID #{{ product.id }}</span>
              <span>外部 ID {{ product.external_id }}</span>
              <span>分类 {{ product.category || '—' }}</span>
              <span>选择器 {{ product.selector_version }}</span>
              <span>创建于 {{ formatDateTime(product.created_at) }}</span>
              <a
                v-if="isHttpUrl"
                :href="product.url"
                target="_blank"
                rel="noopener noreferrer"
                class="link"
              >
                打开商品页
              </a>
              <span v-else class="mono">{{ product.url }}</span>
            </div>

            <div class="detail-prices">
              <div class="price-block">
                <div class="price-block__label">当前价</div>
                <div
                  class="price-block__value"
                  :class="{
                    'price-achieved':
                      product.current_price !== null &&
                      product.target_price !== null &&
                      product.current_price <= product.target_price,
                  }"
                >
                  {{ formatMoney(product.current_price) }}
                </div>
              </div>

              <div class="price-block">
                <div class="price-block__label">目标价</div>
                <div class="price-block__value price-block__value--sm">
                  {{ formatMoney(product.target_price) }}
                </div>
                <div class="price-edit">
                  <el-input-number
                    v-model="targetDraft"
                    :min="0.01"
                    :precision="2"
                    :step="1"
                    :controls="false"
                    size="small"
                    placeholder="未设置"
                    style="width: 104px"
                  />
                  <el-button
                    size="small"
                    type="primary"
                    :loading="savingTarget"
                    @click="saveTargetPrice(false)"
                  >
                    保存
                  </el-button>
                  <el-button
                    v-if="product.target_price !== null"
                    text
                    size="small"
                    :loading="savingTarget"
                    @click="saveTargetPrice(true)"
                  >
                    清除
                  </el-button>
                </div>
              </div>

              <div class="price-block">
                <div class="price-block__label">最近采集</div>
                <div class="price-block__value price-block__value--sm">
                  {{ formatDateTime(product.last_collected_at) }}
                </div>
              </div>

              <div class="price-block">
                <div class="price-block__label">启用状态</div>
                <div class="flex-center mt-8">
                  <el-switch
                    :model-value="product.enabled"
                    :loading="togglingEnabled"
                    :disabled="togglingEnabled"
                    @change="onEnabledChange"
                  />
                  <span class="text-secondary">{{ product.enabled ? '已启用' : '已停用' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-else-if="loading" class="panel">
      <div class="panel-body">
        <el-skeleton :rows="4" animated />
      </div>
    </section>

    <template v-if="product">
      <div class="detail-grid">
        <section class="panel chart-panel">
          <div class="panel-head">
            <div>
              <div class="panel-title">
                <el-icon><TrendCharts /></el-icon>
                价格走势
              </div>
              <div class="panel-subtitle">
                {{ priceSubtitle }} · 金额单位 {{ currencyLabel }}
              </div>
            </div>
            <div class="panel-actions">
              <el-radio-group v-model="range" size="small">
                <el-radio-button value="24h">24 小时</el-radio-button>
                <el-radio-button value="7d">7 天</el-radio-button>
                <el-radio-button value="30d">30 天</el-radio-button>
              </el-radio-group>
              <el-radio-group v-model="granularity" size="small">
                <el-radio-button value="raw">原始</el-radio-button>
                <el-radio-button value="1h">1h</el-radio-button>
                <el-radio-button value="1d">1d</el-radio-button>
              </el-radio-group>
            </div>
          </div>
          <div class="panel-body">
            <PriceChart
              :points="prices?.points ?? []"
              :target-price="prices?.target_price ?? product.target_price"
              :granularity="granularity"
              :currency="prices?.currency ?? 'CNY'"
              :loading="priceLoading"
              :error="priceError"
              :downsampled="prices?.downsampled ?? false"
              :range-from="prices?.from ?? ''"
              :range-to="prices?.to ?? ''"
              @retry="loadPrices(false)"
            />
          </div>
        </section>

        <div class="detail-side">
          <section class="panel">
            <div class="panel-head">
              <div>
                <div class="panel-title">
                  <el-icon><Timer /></el-icon>
                  采集计划
                </div>
                <div class="panel-subtitle">
                  间隔、超时与重试策略
                </div>
              </div>
              <StatusTag :status="product.task?.status" kind="task" />
            </div>

            <div v-if="product.task" class="panel-body">
              <el-form label-position="top" size="default" @submit.prevent="saveTask">
                <el-form-item label="采集间隔（秒）">
                  <el-input-number
                    v-model="taskForm.interval_sec"
                    :min="60"
                    :max="604800"
                    :step="60"
                    controls-position="right"
                    class="full-width"
                  />
                </el-form-item>
                <el-form-item label="单次超时（秒）">
                  <el-input-number
                    v-model="taskForm.timeout_sec"
                    :min="30"
                    :max="1800"
                    :step="30"
                    controls-position="right"
                    class="full-width"
                  />
                </el-form-item>
                <div class="form-grid">
                  <el-form-item label="最大重试">
                    <el-input-number
                      v-model="taskForm.max_retry"
                      :min="0"
                      :max="10"
                      controls-position="right"
                      class="full-width"
                    />
                  </el-form-item>
                  <el-form-item label="优先级">
                    <el-input-number
                      v-model="taskForm.priority"
                      :min="1"
                      :max="9"
                      controls-position="right"
                      class="full-width"
                    />
                  </el-form-item>
                </div>
              </el-form>

              <div class="info-list mt-8">
                <div class="info-row">
                  <span class="info-row__label">调度方式</span>
                  <span class="info-row__value">
                    {{ product.task.schedule_type === 'cron' ? 'Cron 表达式' : '固定间隔' }}
                  </span>
                </div>
                <div class="info-row">
                  <span class="info-row__label">下次执行</span>
                  <span class="info-row__value">{{ formatDateTime(product.task.next_run_at) }}</span>
                </div>
                <div class="info-row">
                  <span class="info-row__label">上次执行</span>
                  <span class="info-row__value">{{ formatDateTime(product.task.last_run_at) }}</span>
                </div>
                <div v-if="product.task.cron_expr" class="info-row">
                  <span class="info-row__label">Cron</span>
                  <span class="info-row__value mono">{{ product.task.cron_expr }}</span>
                </div>
              </div>

              <div class="config-actions">
                <el-button type="primary" size="small" :loading="taskSaving" @click="saveTask">
                  保存配置
                </el-button>
                <el-button
                  size="small"
                  :type="product.task.status === 'active' ? 'warning' : 'success'"
                  :loading="taskActionBusy"
                  @click="toggleTaskStatus"
                >
                  {{ product.task.status === 'active' ? '暂停计划' : '恢复计划' }}
                </el-button>
                <el-button
                  size="small"
                  :icon="VideoPlay"
                  :loading="running"
                  :disabled="product.task.status !== 'active' || !product.enabled"
                  @click="runNow"
                >
                  立即采集
                </el-button>
              </div>
            </div>
            <el-empty v-else description="暂无采集计划" />
          </section>

          <section class="panel">
            <div class="panel-head panel-head--plain">
              <div class="panel-title">
                <el-icon><Aim /></el-icon>
                监控提示
              </div>
            </div>
            <div class="panel-body panel-body--tight">
              <div class="hint-card">
                目标价会以虚线标注在价格曲线中；当当前价低于目标价时，列表与详情页会以绿色高亮。
                采集计划保存后由调度器异步生效，可点击“立即采集”投递一次即时任务。
              </div>
            </div>
          </section>
        </div>
      </div>

      <section class="panel">
        <div class="panel-head">
          <div>
            <div class="panel-title">
              <el-icon><Tickets /></el-icon>
              执行记录
            </div>
            <div class="panel-subtitle">该商品最近的采集执行，点击行查看 trace 与错误详情</div>
          </div>
          <el-button text :icon="Refresh" @click="loadRuns(true, false)">刷新</el-button>
        </div>

        <div class="panel-body panel-body--flush">
          <ErrorBanner
            v-if="runsError"
            title="执行记录加载失败"
            :message="runsError"
            @retry="loadRuns(true, false)"
          />
          <el-table
            v-loading="runsLoading"
            :data="runs"
            :row-class-name="rowClassName"
            style="width: 100%"
            @row-click="openRun"
          >
            <el-table-column prop="id" label="ID" width="82">
              <template #default="{ row }">
                <span class="mono">#{{ row.id }}</span>
              </template>
            </el-table-column>
            <el-table-column label="计划时间" width="170">
              <template #default="{ row }">{{ formatDateTime(row.slot_at) }}</template>
            </el-table-column>
            <el-table-column label="状态" width="96">
              <template #default="{ row }">
                <StatusTag :status="row.status" />
              </template>
            </el-table-column>
            <el-table-column label="尝试" width="72" align="center">
              <template #default="{ row }">第 {{ row.attempt }} 次</template>
            </el-table-column>
            <el-table-column label="耗时" width="104">
              <template #default="{ row }">{{ formatDuration(row.duration_ms) }}</template>
            </el-table-column>
            <el-table-column label="Worker" min-width="130" show-overflow-tooltip>
              <template #default="{ row }">{{ row.worker_id || '—' }}</template>
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
                v-if="!runsLoading && !runsError"
                :image-size="74"
                description="暂无执行记录"
              />
              <span v-else-if="!runsLoading" class="muted">暂无数据</span>
            </template>
          </el-table>

          <div v-if="runsTotal > 0" class="table-footer">
            <span class="table-footer__total">共 {{ runsTotal }} 条执行记录</span>
            <el-pagination
              v-model:current-page="runsPage"
              v-model:page-size="runsPageSize"
              :total="runsTotal"
              :page-sizes="[10, 20, 50]"
              layout="sizes, prev, pager, next"
              background
              @current-change="handleRunsPage"
              @size-change="handleRunsSize"
            />
          </div>
        </div>
      </section>
    </template>

    <RunDrawer v-model="drawerVisible" :run-id="selectedRunId" />
  </div>
</template>

<script setup lang="ts">
import {
  Aim,
  Back,
  Refresh,
  Tickets,
  Timer,
  TrendCharts,
  VideoPlay,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  disableProduct,
  enableProduct,
  getProduct,
  getProductPrices,
  getProductRuns,
  runProduct,
  updateProduct,
} from '@/api/products'
import { pauseTask, resumeTask, updateTask } from '@/api/tasks'
import type { PriceGranularity, PriceSeries, Product, Run } from '@/api/types'
import ErrorBanner from '@/components/ErrorBanner.vue'
import PriceChart from '@/components/PriceChart.vue'
import RunDrawer from '@/components/RunDrawer.vue'
import StatusTag from '@/components/StatusTag.vue'
import {
  currencySymbol,
  errorMessage,
  formatDateTime,
  formatDuration,
  formatMoney,
} from '@/utils/format'

type RangeKey = '24h' | '7d' | '30d'

const route = useRoute()
const router = useRouter()

const productId = computed(() => Number(route.params.id))
const product = ref<Product | null>(null)
const loading = ref(true)
const error = ref('')
const refreshing = ref(false)
const running = ref(false)
const togglingEnabled = ref(false)

const targetDraft = ref<number | undefined>(undefined)
const savingTarget = ref(false)

const prices = ref<PriceSeries | null>(null)
const priceLoading = ref(true)
const priceError = ref('')
const range = ref<RangeKey>('24h')
const granularity = ref<PriceGranularity>('raw')

const runs = ref<Run[]>([])
const runsTotal = ref(0)
const runsPage = ref(1)
const runsPageSize = ref(10)
const runsLoading = ref(true)
const runsError = ref('')

const drawerVisible = ref(false)
const selectedRunId = ref<number | null>(null)

const taskForm = reactive({
  interval_sec: 1800,
  timeout_sec: 300,
  max_retry: 3,
  priority: 5,
})
const taskSaving = ref(false)
const taskActionBusy = ref(false)

const rangeHours: Record<RangeKey, number> = { '24h': 24, '7d': 24 * 7, '30d': 24 * 30 }
const rangeLabels: Record<RangeKey, string> = { '24h': '最近 24 小时', '7d': '最近 7 天', '30d': '最近 30 天' }
const granularityLabels: Record<PriceGranularity, string> = {
  raw: '原始粒度',
  '1h': '小时聚合',
  '1d': '按天聚合',
}

const isHttpUrl = computed(() => Boolean(product.value?.url?.startsWith('http')))
const currencyLabel = computed(() => {
  const code = prices.value?.currency ?? 'CNY'
  return `${currencySymbol(code)} ${code}`
})
const priceSubtitle = computed(
  () => `${rangeLabels[range.value]} · ${granularityLabels[granularity.value]} · 目标价标注参考`,
)

function rowClassName(): string {
  return 'is-clickable'
}

function syncTaskForm(): void {
  const task = product.value?.task
  if (!task) return
  taskForm.interval_sec = task.interval_sec
  taskForm.timeout_sec = task.timeout_sec
  taskForm.max_retry = task.max_retry
  taskForm.priority = task.priority
}

async function loadProduct(silent = true): Promise<void> {
  loading.value = true
  try {
    const data = await getProduct(productId.value, { silent })
    product.value = data
    targetDraft.value = data.target_price ?? undefined
    syncTaskForm()
    error.value = ''
  } catch (err) {
    error.value = errorMessage(err, '商品信息加载失败')
  } finally {
    loading.value = false
  }
}

async function loadPrices(silent = true): Promise<void> {
  priceLoading.value = true
  try {
    const to = new Date()
    const from = new Date(to.getTime() - rangeHours[range.value] * 3600 * 1000)
    const data = await getProductPrices(
      productId.value,
      {
        from: from.toISOString(),
        to: to.toISOString(),
        granularity: granularity.value,
      },
      { silent },
    )
    prices.value = data
    priceError.value = ''
  } catch (err) {
    priceError.value = errorMessage(err, '价格数据加载失败')
  } finally {
    priceLoading.value = false
  }
}

async function loadRuns(initial = false, silent = true): Promise<void> {
  if (initial) runsLoading.value = true
  try {
    const result = await getProductRuns(
      productId.value,
      { page: runsPage.value, page_size: runsPageSize.value },
      { silent },
    )
    runs.value = result.items
    runsTotal.value = result.total
    runsPage.value = result.page
    runsPageSize.value = result.page_size
    runsError.value = ''
  } catch (err) {
    runsError.value = errorMessage(err, '执行记录加载失败')
  } finally {
    runsLoading.value = false
  }
}

async function initialize(): Promise<void> {
  prices.value = null
  runs.value = []
  runsTotal.value = 0
  runsPage.value = 1
  await loadProduct(false)
  if (product.value) {
    void loadPrices(false)
    void loadRuns(true, false)
  }
}

async function reload(): Promise<void> {
  await loadProduct(false)
  if (product.value) {
    await Promise.allSettled([loadPrices(false), loadRuns(true, false)])
  }
}

async function refreshAll(): Promise<void> {
  refreshing.value = true
  try {
    await reload()
  } finally {
    refreshing.value = false
  }
}

function goBack(): void {
  void router.push('/products')
}

async function runNow(): Promise<void> {
  if (!product.value || running.value) return
  running.value = true
  try {
    const result = await runProduct(product.value.id)
    ElMessage.success(`已提交采集任务（run #${result.run_id}）`)
  } catch {
    // 请求层已提示
  } finally {
    running.value = false
  }
}

function onEnabledChange(value: string | number | boolean): void {
  void toggleEnabled(Boolean(value))
}

async function toggleEnabled(enabled: boolean): Promise<void> {  if (!product.value || togglingEnabled.value) return
  togglingEnabled.value = true
  try {
    const updated = enabled
      ? await enableProduct(product.value.id)
      : await disableProduct(product.value.id)
    product.value = updated
    targetDraft.value = updated.target_price ?? undefined
    syncTaskForm()
    ElMessage.success(enabled ? '商品已启用' : '商品已停用')
  } catch {
    // 请求体失败时保持原状态
  } finally {
    togglingEnabled.value = false
  }
}

async function saveTargetPrice(clear = false): Promise<void> {
  if (!product.value || savingTarget.value) return
  if (!clear && (!targetDraft.value || targetDraft.value <= 0)) {
    ElMessage.warning('请输入大于 0 的目标价，或点击「清除」移除目标价')
    return
  }
  const value = clear ? null : targetDraft.value && targetDraft.value > 0 ? targetDraft.value : null
  savingTarget.value = true
  try {
    const updated = await updateProduct(product.value.id, { target_price: value })
    product.value = updated
    targetDraft.value = updated.target_price ?? undefined
    ElMessage.success(clear ? '目标价已清除' : '目标价已更新')
    void loadPrices(true)
  } catch {
    // 请求层已提示
  } finally {
    savingTarget.value = false
  }
}

async function saveTask(): Promise<void> {
  const task = product.value?.task
  if (!task || taskSaving.value) return
  if (
    !Number.isFinite(taskForm.interval_sec) ||
    !Number.isFinite(taskForm.timeout_sec) ||
    !Number.isFinite(taskForm.max_retry) ||
    !Number.isFinite(taskForm.priority)
  ) {
    ElMessage.warning('请填写完整的计划参数')
    return
  }
  if (taskForm.interval_sec < 60 || taskForm.timeout_sec < 30) {
    ElMessage.warning('采集间隔不能小于 60 秒，超时不能小于 30 秒')
    return
  }
  taskSaving.value = true
  try {
    const updated = await updateTask(task.id, {
      interval_sec: taskForm.interval_sec,
      timeout_sec: taskForm.timeout_sec,
      max_retry: taskForm.max_retry,
      priority: taskForm.priority,
    })
    if (product.value) product.value = { ...product.value, task: updated }
    ElMessage.success('采集计划已更新')
  } catch {
    // 请求层已提示
  } finally {
    taskSaving.value = false
  }
}

async function toggleTaskStatus(): Promise<void> {
  const task = product.value?.task
  if (!task || taskActionBusy.value) return
  taskActionBusy.value = true
  try {
    const updated = task.status === 'active' ? await pauseTask(task.id) : await resumeTask(task.id)
    if (product.value) product.value = { ...product.value, task: updated }
    ElMessage.success(task.status === 'active' ? '采集计划已暂停' : '采集计划已恢复')
  } catch {
    // 请求层已提示
  } finally {
    taskActionBusy.value = false
  }
}

function handleRunsPage(value: number): void {
  runsPage.value = value
  void loadRuns(true, false)
}

function handleRunsSize(value: number): void {
  runsPageSize.value = value
  runsPage.value = 1
  void loadRuns(true, false)
}

function openRun(row: Run): void {
  selectedRunId.value = row.id
  drawerVisible.value = true
}

watch([range, granularity], () => {
  void loadPrices(false)
})

watch(productId, (next, previous) => {
  if (next !== previous) void initialize()
})

onMounted(() => {
  void initialize()
})
</script>
