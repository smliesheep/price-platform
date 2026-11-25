<template>
  <el-drawer
    v-model="visible"
    title="执行记录详情"
    size="min(580px, 94vw)"
    :destroy-on-close="false"
    class="run-drawer"
  >
    <div v-loading="loading" class="drawer-body">
      <ErrorBanner v-if="error" title="执行记录加载失败" :message="error" @retry="reload" />

      <template v-if="run">
        <div class="run-summary">
          <el-tag size="small" effect="dark" type="info">#{{ run.id }}</el-tag>
          <StatusTag :status="run.status" />
          <span class="muted">
            {{ run.product_title || `商品 #${run.product_id}` }}
          </span>
          <span class="muted">·</span>
          <span class="muted">{{ formatDuration(run.duration_ms) }}</span>
        </div>

        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="执行 ID">{{ run.id }}</el-descriptions-item>
          <el-descriptions-item label="任务 ID">{{ run.task_id }}</el-descriptions-item>
          <el-descriptions-item label="商品">
            <span class="link" @click="openProduct">
              {{ run.product_title || `商品 #${run.product_id}` }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="商品 ID">{{ run.product_id }}</el-descriptions-item>
          <el-descriptions-item label="Worker">{{ run.worker_id || '—' }}</el-descriptions-item>
          <el-descriptions-item label="尝试次数">第 {{ run.attempt }} 次</el-descriptions-item>
          <el-descriptions-item label="计划时间">{{ formatDateTime(run.slot_at) }}</el-descriptions-item>
          <el-descriptions-item label="HTTP 状态">
            <span :class="httpClass(run.http_status)">{{ run.http_status ?? '—' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="排队时间">{{ formatDateTime(run.queued_at) }}</el-descriptions-item>
          <el-descriptions-item label="开始时间">{{ formatDateTime(run.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束时间">{{ formatDateTime(run.finished_at) }}</el-descriptions-item>
          <el-descriptions-item label="耗时">{{ formatDuration(run.duration_ms) }}</el-descriptions-item>
          <el-descriptions-item label="错误类型">{{ run.error_type || '—' }}</el-descriptions-item>
          <el-descriptions-item label="Trace ID" :span="2">
            <span class="copy-field">
              <span class="mono">{{ run.trace_id || '—' }}</span>
              <el-button
                v-if="run.trace_id"
                text
                size="small"
                :icon="CopyDocument"
                aria-label="复制 Trace ID"
                @click="copyTrace"
              />
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="商品链接" :span="2">
            <a
              v-if="isHttpUrl"
              :href="run.product_url ?? '#'"
              target="_blank"
              rel="noopener noreferrer"
              class="link mono"
            >
              {{ run.product_url }}
            </a>
            <span v-else class="mono muted">{{ run.product_url || '—' }}</span>
          </el-descriptions-item>
        </el-descriptions>

        <div v-if="run.error_msg" class="error-detail">
          <div class="error-detail__label">错误信息</div>
          <pre>{{ run.error_msg }}</pre>
        </div>

        <div class="drawer-actions">
          <el-button size="small" :icon="Refresh" @click="reload">刷新</el-button>
          <el-button size="small" type="primary" :icon="Goods" @click="openProduct">
            查看商品
          </el-button>
        </div>
      </template>

      <el-empty
        v-else-if="!loading && !error"
        :image-size="80"
        description="未找到执行记录"
      />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { CopyDocument, Goods, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { getRun } from '@/api/runs'
import type { RunDetail } from '@/api/types'
import ErrorBanner from '@/components/ErrorBanner.vue'
import StatusTag from '@/components/StatusTag.vue'
import { copyToClipboard, errorMessage, formatDateTime, formatDuration } from '@/utils/format'

const props = defineProps<{
  modelValue: boolean
  runId: number | null
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
}>()

const router = useRouter()
const run = ref<RunDetail | null>(null)
const loading = ref(false)
const error = ref('')

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const isHttpUrl = computed(() => Boolean(run.value?.product_url?.startsWith('http')))

async function load(id: number): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    run.value = await getRun(id, { silent: true })
  } catch (err) {
    run.value = null
    error.value = errorMessage(err, '执行记录加载失败')
  } finally {
    loading.value = false
  }
}

function reload(): void {
  if (props.runId) void load(props.runId)
}

function httpClass(status: number | null): string {
  if (status === null) return 'muted'
  if (status >= 200 && status < 300) return 'text-success'
  if (status >= 500) return 'text-danger'
  if (status >= 400) return 'text-warning'
  return ''
}

async function copyTrace(): Promise<void> {
  if (!run.value?.trace_id) return
  const done = await copyToClipboard(run.value.trace_id)
  if (done) ElMessage.success('Trace ID 已复制')
  else ElMessage.error('复制失败，请手动选择复制')
}

async function openProduct(): Promise<void> {
  if (!run.value) return
  visible.value = false
  await router.push(`/products/${run.value.product_id}`)
}

watch(
  () => [props.modelValue, props.runId] as const,
  ([open, id]) => {
    if (open && typeof id === 'number') void load(id)
  },
  { immediate: true },
)
</script>
