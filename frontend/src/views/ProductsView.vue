<template>
  <div class="page">
    <div class="page-head">
      <div class="page-head__title">
        <h2>商品</h2>
        <p>管理监控商品、目标价与采集启停</p>
      </div>
      <div class="page-head__actions">
        <el-button :icon="Refresh" :loading="refreshing" @click="refresh">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openCreate">新增商品</el-button>
      </div>
    </div>

    <div class="filter-bar">
      <div class="filter-item filter-item--wide">
        <span class="filter-item__label">关键词</span>
        <el-input
          v-model="filters.q"
          placeholder="搜索商品标题"
          clearable
          :prefix-icon="Search"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
      </div>
      <div class="filter-item">
        <span class="filter-item__label">启用状态</span>
        <el-select v-model="filters.enabled" placeholder="全部">
          <el-option label="全部" value="" />
          <el-option label="已启用" value="enabled" />
          <el-option label="已停用" value="disabled" />
        </el-select>
      </div>
      <div class="filter-item">
        <span class="filter-item__label">来源站点</span>
        <el-select
          v-model="filters.source_id"
          placeholder="全部来源"
          clearable
          :loading="sourcesLoading"
        >
          <el-option
            v-for="source in sources"
            :key="source.id"
            :label="`${source.name}${source.enabled ? '' : '（停用）'}`"
            :value="source.id"
          />
        </el-select>
        <span v-if="sourcesError" class="form-hint text-danger">来源加载失败</span>
      </div>
      <div class="filter-actions">
        <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
        <el-button :icon="RefreshLeft" @click="handleReset">重置</el-button>
      </div>
    </div>

    <ErrorBanner
      v-if="error"
      title="商品列表加载失败"
      :message="error"
      @retry="refresh"
    />

    <section class="panel">
      <div class="panel-body panel-body--flush">
        <el-table v-loading="loading" :data="rows" style="width: 100%">
          <el-table-column label="商品" min-width="290">
            <template #default="{ row }">
              <router-link :to="`/products/${row.id}`" class="table-title link link--title">
                {{ row.title }}
              </router-link>
              <div class="table-sub">
                {{ row.source_name || '未知来源' }} · {{ row.external_id }}
                <template v-if="row.category"> · {{ row.category }}</template>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="当前价" width="120">
            <template #default="{ row }">
              <span
                class="nums"
                :class="{
                  'price-achieved':
                    row.current_price !== null &&
                    row.target_price !== null &&
                    row.current_price <= row.target_price,
                }"
              >
                {{ formatMoney(row.current_price) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="目标价" width="120">
            <template #default="{ row }">
              <span class="nums text-secondary">{{ formatMoney(row.target_price) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最近采集" width="170">
            <template #default="{ row }">
              <span class="muted">{{ formatDateTime(row.last_collected_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="最近状态" width="106">
            <template #default="{ row }">
              <StatusTag :status="row.last_status" kind="product" />
            </template>
          </el-table-column>
          <el-table-column label="启用" width="84" align="center">
            <template #default="{ row }">
              <el-switch
                :model-value="row.enabled"
                :loading="togglingIds.has(row.id)"
                :disabled="togglingIds.has(row.id)"
                @change="toggleProduct(row, $event)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="248">
            <template #default="{ row }">
              <div class="table-actions">
                <el-button link type="primary" size="small" @click="goDetail(row)">
                  详情
                </el-button>
                <el-button
                  link
                  type="primary"
                  size="small"
                  :loading="runningIds.has(row.id)"
                  :disabled="!row.enabled || row.task?.status !== 'active'"
                  :title="row.task?.status !== 'active' ? '采集计划已暂停，请先在任务页恢复' : '立即采集'"
                  @click="runNow(row)"
                >
                  立即采集
                </el-button>
                <el-button
                  link
                  :type="row.enabled ? 'warning' : 'success'"
                  size="small"
                  :loading="togglingIds.has(row.id)"
                  @click="toggleProduct(row, !row.enabled)"
                >
                  {{ row.enabled ? '停用' : '启用' }}
                </el-button>
                <el-button
                  link
                  type="danger"
                  size="small"
                  :loading="deletingIds.has(row.id)"
                  @click="removeProduct(row)"
                >
                  删除
                </el-button>
              </div>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty
              v-if="!loading && !error"
              :image-size="82"
              description="暂无商品"
            >
              <el-button type="primary" :icon="Plus" @click="openCreate">新增商品</el-button>
            </el-empty>
            <span v-else-if="!loading" class="muted">暂无数据</span>
          </template>
        </el-table>

        <div v-if="total > 0" class="table-footer">
          <span class="table-footer__total">共 {{ total }} 个商品</span>
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

    <el-dialog
      v-model="createVisible"
      title="新增商品"
      width="560px"
      :close-on-click-modal="false"
      @closed="resetCreate"
    >
      <template v-if="!createdProduct">
        <el-alert
          v-if="createError"
          :title="createError"
          type="error"
          show-icon
          :closable="false"
          class="mb-16"
        />
        <el-form
          ref="createFormRef"
          :model="createForm"
          :rules="createRules"
          label-position="top"
        >
          <div class="form-grid">
            <el-form-item label="来源站点" prop="source_id" class="span-2">
              <el-select
                v-model="createForm.source_id"
                placeholder="请选择站点来源"
                :loading="sourcesLoading"
                class="full-width"
              >
                <el-option
                  v-for="source in sources"
                  :key="source.id"
                  :label="`${source.name}（${source.adapter}）`"
                  :value="source.id"
                  :disabled="!source.enabled"
                />
              </el-select>
              <div v-if="!sourcesLoading && sources.length === 0" class="form-hint text-danger">
                暂无可用来源，请先在后台配置站点。
              </div>
            </el-form-item>

            <el-form-item label="商品 URL" prop="url" class="span-2">
              <el-input
                v-model="createForm.url"
                placeholder="https://shop.example.com/p/123 或 /p/123"
                clearable
              />
              <div class="form-hint">支持相对路径；留空标题时后端会抓取页面解析标题与当前价。</div>
            </el-form-item>

            <el-form-item label="目标价（元）">
              <el-input-number
                v-model="createForm.target_price"
                :min="0.01"
                :precision="2"
                :step="1"
                controls-position="right"
                placeholder="选填"
                class="full-width"
              />
            </el-form-item>

            <el-form-item label="采集间隔（秒）" prop="interval_sec">
              <el-input-number
                v-model="createForm.interval_sec"
                :min="60"
                :max="604800"
                :step="60"
                controls-position="right"
                class="full-width"
              />
              <div class="form-hint">最小 60 秒，默认 1800 秒。</div>
            </el-form-item>

            <el-form-item label="商品标题（选填）" class="span-2">
              <el-input
                v-model="createForm.title"
                placeholder="留空由后端解析"
                clearable
                maxlength="200"
              />
            </el-form-item>
          </div>
        </el-form>
      </template>

      <template v-else>
        <el-alert
          title="商品创建成功"
          type="success"
          show-icon
          :closable="false"
          description="后端已完成 URL 解析并生成采集计划"
        />
        <div class="result-box">
          <div class="muted mt-16">后端解析标题</div>
          <div class="result-title">{{ createdProduct.title }}</div>
          <div class="result-row">
            <span>商品 ID <strong>#{{ createdProduct.id }}</strong></span>
            <span>来源 <strong>{{ createdProduct.source_name || '—' }}</strong></span>
            <span>当前价 <strong>{{ formatMoney(createdProduct.current_price) }}</strong></span>
            <span>目标价 <strong>{{ formatMoney(createdProduct.target_price) }}</strong></span>
            <span>
              采集间隔
              <strong>{{ formatInterval(createdProduct.task?.interval_sec ?? createForm.interval_sec) }}</strong>
            </span>
          </div>
          <div v-if="createdProduct.current_price === null" class="form-hint">
            后端暂未解析到当前价格，标题可能为占位标题，可稍后在详情页修改。
          </div>
        </div>
      </template>

      <template #footer>
        <div v-if="createdProduct" class="dialog-footer">
          <el-button @click="createVisible = false">关闭</el-button>
          <el-button @click="continueCreate">继续新增</el-button>
          <el-button type="primary" @click="viewCreated">查看详情</el-button>
        </div>
        <div v-else class="dialog-footer">
          <el-button @click="createVisible = false">取消</el-button>
          <el-button type="primary" :loading="creating" @click="submitCreate">创建商品</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { Plus, Refresh, RefreshLeft, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  createProduct,
  deleteProduct,
  disableProduct,
  enableProduct,
  getProducts,
  runProduct,
} from '@/api/products'
import { ApiError } from '@/api/http'
import { getSources } from '@/api/sources'
import type { CreateProductPayload, Product, ProductQuery, Source } from '@/api/types'
import ErrorBanner from '@/components/ErrorBanner.vue'
import StatusTag from '@/components/StatusTag.vue'
import { errorMessage, formatDateTime, formatInterval, formatMoney } from '@/utils/format'

const router = useRouter()

const sources = ref<Source[]>([])
const sourcesLoading = ref(false)
const sourcesError = ref('')

const rows = ref<Product[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(true)
const error = ref('')
const refreshing = ref(false)

const filters = reactive({
  q: '',
  enabled: '' as '' | 'enabled' | 'disabled',
  source_id: undefined as number | undefined,
})

const togglingIds = reactive(new Set<number>())
const runningIds = reactive(new Set<number>())
const deletingIds = reactive(new Set<number>())

const createVisible = ref(false)
const creating = ref(false)
const createError = ref('')
const createdProduct = ref<Product | null>(null)
const createFormRef = ref<FormInstance>()
const createForm = reactive({
  source_id: undefined as number | undefined,
  url: '',
  target_price: undefined as number | undefined,
  interval_sec: 1800,
  title: '',
})

const createRules: FormRules = {
  source_id: [{ required: true, message: '请选择来源站点', trigger: 'change' }],
  url: [{ required: true, message: '请填写商品 URL', trigger: 'blur' }],
  interval_sec: [{ required: true, message: '请填写采集间隔', trigger: 'change' }],
}

function buildQuery(): ProductQuery {
  return {
    q: filters.q.trim() || undefined,
    enabled:
      filters.enabled === '' ? undefined : filters.enabled === 'enabled',
    source_id: filters.source_id,
    page: page.value,
    page_size: pageSize.value,
  }
}

async function load(silent = true): Promise<void> {
  loading.value = true
  try {
    const result = await getProducts(buildQuery(), { silent })
    rows.value = result.items
    total.value = result.total
    page.value = result.page
    pageSize.value = result.page_size
    error.value = ''
  } catch (err) {
    error.value = errorMessage(err, '商品列表加载失败')
  } finally {
    loading.value = false
  }
}

async function loadSources(silent = true): Promise<void> {
  sourcesLoading.value = true
  try {
    sources.value = await getSources({ silent })
    sourcesError.value = ''
  } catch (err) {
    sourcesError.value = errorMessage(err, '来源列表加载失败')
  } finally {
    sourcesLoading.value = false
  }
}

async function refresh(): Promise<void> {
  refreshing.value = true
  try {
    await Promise.allSettled([load(false), loadSources(false)])
  } finally {
    refreshing.value = false
  }
}

function handleSearch(): void {
  page.value = 1
  void load(false)
}

function handleReset(): void {
  filters.q = ''
  filters.enabled = ''
  filters.source_id = undefined
  page.value = 1
  void load(false)
}

function handlePageChange(value: number): void {
  page.value = value
  void load(true)
}

function handleSizeChange(value: number): void {
  pageSize.value = value
  page.value = 1
  void load(true)
}

function goDetail(row: Product): void {
  void router.push(`/products/${row.id}`)
}

async function toggleProduct(row: Product, value: string | number | boolean): Promise<void> {
  const enabled = Boolean(value)
  if (togglingIds.has(row.id)) return
  togglingIds.add(row.id)
  try {
    const updated = enabled ? await enableProduct(row.id) : await disableProduct(row.id)
    Object.assign(row, updated)
    ElMessage.success(enabled ? '商品已启用' : '商品已停用')
  } catch {
    // 请求层已提示，保持原状态
  } finally {
    togglingIds.delete(row.id)
  }
}

async function runNow(row: Product): Promise<void> {
  if (runningIds.has(row.id)) return
  runningIds.add(row.id)
  try {
    const result = await runProduct(row.id)
    ElMessage.success(`已提交采集任务（run #${result.run_id}）`)
  } catch {
    // 请求层已提示
  } finally {
    runningIds.delete(row.id)
  }
}

async function removeProduct(row: Product): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除商品「${row.title}」吗？删除后不可恢复。`,
      '删除商品',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return
  }
  deletingIds.add(row.id)
  try {
    await deleteProduct(row.id)
    ElMessage.success('商品已删除')
    if (rows.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    await load(true)
  } catch {
    // 请求层已提示
  } finally {
    deletingIds.delete(row.id)
  }
}

function openCreate(): void {
  resetCreate()
  createVisible.value = true
  void loadSources(true)
}

function resetCreate(): void {
  createdProduct.value = null
  createError.value = ''
  createForm.url = ''
  createForm.title = ''
  createForm.target_price = undefined
  createForm.interval_sec = 1800
  createForm.source_id =
    sources.value.find((source) => source.enabled)?.id ?? sources.value[0]?.id
  void nextTick(() => createFormRef.value?.clearValidate())
}

function continueCreate(): void {
  createdProduct.value = null
  createError.value = ''
  createForm.url = ''
  createForm.title = ''
  createForm.target_price = undefined
  createForm.interval_sec = 1800
  void nextTick(() => createFormRef.value?.clearValidate())
}

function viewCreated(): void {
  if (!createdProduct.value) return
  const id = createdProduct.value.id
  createVisible.value = false
  void router.push(`/products/${id}`)
}

function describeCreateError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) {
      const matched = /id=(\d+)/.exec(error.message)
      return matched
        ? `该商品已存在（对应商品 #${matched[1]}），请勿重复添加`
        : '该商品已存在，请勿重复添加'
    }
    if (error.status === 404) return '来源站点不存在，请刷新页面后重试'
    if (error.status === 422) return '表单校验失败，请检查 URL、目标价与采集间隔'
  }
  return errorMessage(error, '创建商品失败')
}

async function submitCreate(): Promise<void> {
  if (!createFormRef.value || creating.value) return
  const valid = await createFormRef.value.validate().catch(() => false)
  if (!valid || !createForm.source_id) return

  const url = createForm.url.trim()
  if (!url) {
    createError.value = '请填写商品 URL'
    ElMessage.warning(createError.value)
    return
  }
  if (!createForm.interval_sec || createForm.interval_sec < 60) {
    createError.value = '采集间隔不能小于 60 秒'
    ElMessage.warning(createError.value)
    return
  }

  creating.value = true
  createError.value = ''
  try {
    const payload: CreateProductPayload = {
      source_id: createForm.source_id,
      url,
      interval_sec: createForm.interval_sec,
      title: createForm.title.trim() || undefined,
      target_price:
        createForm.target_price && createForm.target_price > 0
          ? createForm.target_price
          : undefined,
    }
    const created = await createProduct(payload, { silent: true })
    createdProduct.value = created
    ElMessage.success(`商品创建成功：${created.title}`)
    page.value = 1
    void load(true)
    void loadSources(true)
  } catch (err) {
    createError.value = describeCreateError(err)
    ElMessage.error(createError.value)
  } finally {
    creating.value = false
  }
}

onMounted(() => {
  void load(false)
  void loadSources(true)
})
</script>
