<template>
  <div class="page">
    <div class="page-head">
      <div class="page-head__title">
        <h2>任务</h2>
        <p>采集计划状态、执行时间与优先级 · 每 30 秒自动刷新</p>
      </div>
      <div class="page-head__actions">
        <el-radio-group v-model="statusFilter" @change="handleStatusChange">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="active">运行中</el-radio-button>
          <el-radio-button value="paused">已暂停</el-radio-button>
          <el-radio-button value="archived">已归档</el-radio-button>
        </el-radio-group>
        <el-button :icon="Refresh" :loading="loading" @click="load(true, false)">刷新</el-button>
      </div>
    </div>

    <ErrorBanner v-if="error" title="任务列表加载失败" :message="error" @retry="load(true, false)" />

    <section class="panel">
      <div class="panel-body panel-body--flush">
        <el-table v-loading="loading" :data="rows" style="width: 100%">
          <el-table-column label="商品" min-width="260">
            <template #default="{ row }">
              <router-link
                :to="`/products/${row.product_id}`"
                class="table-title link link--title"
              >
                {{ row.product_title || `商品 #${row.product_id}` }}
              </router-link>
              <div class="table-sub">任务 #{{ row.id }} · 商品 #{{ row.product_id }}</div>
            </template>
          </el-table-column>
          <el-table-column label="间隔" width="128">
            <template #default="{ row }">
              <span class="nums">{{ formatInterval(row.interval_sec) }}</span>
              <div class="table-sub">{{ row.schedule_type === 'cron' ? 'Cron' : '固定间隔' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="下次执行" width="170">
            <template #default="{ row }">
              <span class="muted">{{ formatDateTime(row.next_run_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="上次执行" width="170">
            <template #default="{ row }">
              <span class="muted">{{ formatDateTime(row.last_run_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="96">
            <template #default="{ row }">
              <StatusTag :status="row.status" kind="task" />
            </template>
          </el-table-column>
          <el-table-column label="优先级" width="82" align="center">
            <template #default="{ row }">
              <el-tag size="small" effect="plain" type="info">P{{ row.priority }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="236">
            <template #default="{ row }">
              <div class="table-actions">
                <el-button
                  link
                  type="primary"
                  size="small"
                  :icon="VideoPlay"
                  :loading="runningIds.has(row.id)"
                  :disabled="row.status !== 'active'"
                  @click="runNow(row)"
                >
                  执行
                </el-button>
                <el-button
                  v-if="row.status !== 'archived'"
                  link
                  :type="row.status === 'active' ? 'warning' : 'success'"
                  size="small"
                  :icon="row.status === 'active' ? VideoPause : VideoPlay"
                  :loading="actionIds.has(row.id)"
                  @click="toggleStatus(row)"
                >
                  {{ row.status === 'active' ? '暂停' : '恢复' }}
                </el-button>
                <el-button
                  link
                  type="primary"
                  size="small"
                  :icon="Edit"
                  @click="openEdit(row)"
                >
                  编辑
                </el-button>
              </div>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty
              v-if="!loading && !error"
              :image-size="80"
              description="暂无采集任务"
            />
            <span v-else-if="!loading" class="muted">暂无数据</span>
          </template>
        </el-table>

        <div v-if="total > 0" class="table-footer">
          <span class="table-footer__total">共 {{ total }} 个任务</span>
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
      v-model="editVisible"
      title="编辑采集计划"
      width="520px"
      :close-on-click-modal="false"
    >
      <div v-if="editingTask" class="mb-12">
        <div class="table-title">{{ editingTask.product_title || `商品 #${editingTask.product_id}` }}</div>
        <div class="table-sub">
          任务 #{{ editingTask.id }} · 当前状态
          {{ editingTask.status === 'active' ? '运行中' : editingTask.status === 'paused' ? '已暂停' : '已归档' }}
        </div>
      </div>

      <el-form label-position="top" @submit.prevent="saveEdit">
        <div class="form-grid">
          <el-form-item label="采集间隔（秒）">
            <el-input-number
              v-model="editForm.interval_sec"
              :min="60"
              :max="604800"
              :step="60"
              controls-position="right"
              class="full-width"
            />
          </el-form-item>
          <el-form-item label="单次超时（秒）">
            <el-input-number
              v-model="editForm.timeout_sec"
              :min="30"
              :max="1800"
              :step="30"
              controls-position="right"
              class="full-width"
            />
          </el-form-item>
          <el-form-item label="最大重试次数">
            <el-input-number
              v-model="editForm.max_retry"
              :min="0"
              :max="10"
              controls-position="right"
              class="full-width"
            />
          </el-form-item>
          <el-form-item label="优先级">
            <el-input-number
              v-model="editForm.priority"
              :min="1"
              :max="9"
              controls-position="right"
              class="full-width"
            />
          </el-form-item>
        </div>
        <div class="form-hint">间隔范围 60 秒 ~ 7 天；超时范围 30 ~ 1800 秒；保存后调度器会重新计算下次执行时间。</div>
      </el-form>

      <template #footer>
        <div class="dialog-footer">
          <el-button @click="editVisible = false">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { Edit, Refresh, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'

import { getTasks, pauseTask, resumeTask, runTask, updateTask } from '@/api/tasks'
import type { TaskItem } from '@/api/types'
import ErrorBanner from '@/components/ErrorBanner.vue'
import StatusTag from '@/components/StatusTag.vue'
import { usePolling } from '@/composables/usePolling'
import { errorMessage, formatDateTime, formatInterval } from '@/utils/format'

const rows = ref<TaskItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(true)
const error = ref('')
const statusFilter = ref<'' | 'active' | 'paused' | 'archived'>('')

const runningIds = reactive(new Set<number>())
const actionIds = reactive(new Set<number>())

const editVisible = ref(false)
const editingTask = ref<TaskItem | null>(null)
const saving = ref(false)
const editForm = reactive({
  interval_sec: 1800,
  timeout_sec: 300,
  max_retry: 3,
  priority: 5,
})

async function load(initial = false, silent = true): Promise<void> {
  if (initial) loading.value = true
  try {
    const result = await getTasks(
      {
        status: statusFilter.value || undefined,
        page: page.value,
        page_size: pageSize.value,
      },
      { silent },
    )
    rows.value = result.items
    total.value = result.total
    page.value = result.page
    pageSize.value = result.page_size
    error.value = ''
  } catch (err) {
    error.value = errorMessage(err, '任务列表加载失败')
  } finally {
    loading.value = false
  }
}

function handleStatusChange(): void {
  page.value = 1
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

async function runNow(row: TaskItem): Promise<void> {
  if (runningIds.has(row.id)) return
  runningIds.add(row.id)
  try {
    const result = await runTask(row.id)
    ElMessage.success(`已提交执行（run #${result.run_id}）`)
    void load(false, true)
  } catch {
    // 请求层已提示
  } finally {
    runningIds.delete(row.id)
  }
}

async function toggleStatus(row: TaskItem): Promise<void> {
  if (actionIds.has(row.id)) return
  const wasActive = row.status === 'active'
  actionIds.add(row.id)
  try {
    const updated = wasActive ? await pauseTask(row.id) : await resumeTask(row.id)
    Object.assign(row, updated)
    ElMessage.success(wasActive ? '任务已暂停' : '任务已恢复')
    void load(false, true)
  } catch {
    // 请求层已提示
  } finally {
    actionIds.delete(row.id)
  }
}

function openEdit(row: TaskItem): void {
  editingTask.value = row
  editForm.interval_sec = row.interval_sec
  editForm.timeout_sec = row.timeout_sec
  editForm.max_retry = row.max_retry
  editForm.priority = row.priority
  editVisible.value = true
}

async function saveEdit(): Promise<void> {
  if (!editingTask.value || saving.value) return
  if (
    !Number.isFinite(editForm.interval_sec) ||
    !Number.isFinite(editForm.timeout_sec) ||
    !Number.isFinite(editForm.max_retry) ||
    !Number.isFinite(editForm.priority)
  ) {
    ElMessage.warning('请填写完整的任务参数')
    return
  }
  if (editForm.interval_sec < 60 || editForm.timeout_sec < 30) {
    ElMessage.warning('采集间隔不能小于 60 秒，超时不能小于 30 秒')
    return
  }
  saving.value = true
  try {
    const updated = await updateTask(editingTask.value.id, {
      interval_sec: editForm.interval_sec,
      timeout_sec: editForm.timeout_sec,
      max_retry: editForm.max_retry,
      priority: editForm.priority,
    })
    const index = rows.value.findIndex((item) => item.id === updated.id)
    if (index >= 0) {
      rows.value[index] = { ...rows.value[index], ...updated }
    }
    ElMessage.success('任务配置已更新')
    editVisible.value = false
  } catch {
    // 请求层已提示
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  void load(true, false)
})

usePolling(() => load(false, true), 30_000)
</script>
