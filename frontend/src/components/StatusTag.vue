<template>
  <el-tag :type="meta.type" size="small" effect="light" round>{{ meta.label }}</el-tag>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type TagType = 'primary' | 'success' | 'info' | 'warning' | 'danger'
type StatusKind = 'run' | 'task' | 'product'

const props = withDefaults(
  defineProps<{
    status?: string | null
    kind?: StatusKind
  }>(),
  {
    status: null,
    kind: 'run',
  },
)

const runMap: Record<string, { label: string; type: TagType }> = {
  queued: { label: '排队中', type: 'info' },
  running: { label: '执行中', type: 'primary' },
  success: { label: '成功', type: 'success' },
  failed: { label: '失败', type: 'danger' },
  timeout: { label: '超时', type: 'warning' },
  canceled: { label: '已取消', type: 'info' },
  retry_wait: { label: '等待重试', type: 'warning' },
}

const taskMap: Record<string, { label: string; type: TagType }> = {
  active: { label: '运行中', type: 'success' },
  paused: { label: '已暂停', type: 'info' },
  archived: { label: '已归档', type: 'info' },
}

const productMap: Record<string, { label: string; type: TagType }> = {
  success: { label: '采集成功', type: 'success' },
  failed: { label: '采集失败', type: 'danger' },
  timeout: { label: '采集超时', type: 'warning' },
  running: { label: '采集中', type: 'primary' },
  queued: { label: '待采集', type: 'info' },
}

const meta = computed<{ label: string; type: TagType }>(() => {
  const value = (props.status ?? '').trim()
  if (!value) return { label: '未采集', type: 'info' }
  const map = props.kind === 'task' ? taskMap : props.kind === 'product' ? productMap : runMap
  return map[value] ?? { label: value, type: 'info' }
})
</script>
