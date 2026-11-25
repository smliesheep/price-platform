<template>
  <div class="queue-gauge">
    <div class="queue-gauge__head">
      <div class="queue-gauge__total">
        积压构成合计
        <strong>{{ formatNumber(total) }}</strong>
      </div>
      <el-tag size="small" effect="plain" type="info">
        Stream length {{ formatNumber(queue?.length) }}
      </el-tag>
    </div>

    <el-skeleton v-if="loading" :rows="2" animated />

    <template v-else>
      <div class="queue-bar" role="img" :aria-label="`队列积压 ${total}`">
        <div
          v-for="segment in segments"
          :key="segment.key"
          class="queue-bar__segment"
          :style="{ width: segment.width, background: segment.color }"
          :title="`${segment.name}：${segment.value}`"
        />
        <div v-if="segments.length === 0" class="queue-bar__idle" />
      </div>

      <div class="queue-legend">
        <div v-for="item in legend" :key="item.key" class="queue-legend__item">
          <div class="queue-legend__name">
            <span class="queue-legend__dot" :style="{ background: item.color }" />
            {{ item.name }}
          </div>
          <div class="queue-legend__value">{{ formatNumber(item.value) }}</div>
        </div>
      </div>

      <div class="queue-foot">
        <span>队列长度：{{ formatNumber(queue?.length) }}</span>
        <span>消费者组：{{ group || '—' }}</span>
        <span>数据定期刷新</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import type { QueueStats } from '@/api/types'
import { formatNumber } from '@/utils/format'

const props = withDefaults(
  defineProps<{
    queue?: QueueStats | null
    loading?: boolean
    group?: string
  }>(),
  {
    queue: null,
    loading: false,
    group: '',
  },
)

interface LegendItem {
  key: string
  name: string
  value: number
  color: string
}

const legend = computed<LegendItem[]>(() => {
  const queue = props.queue
  return [
    { key: 'pending', name: '待投递', value: queue?.pending ?? 0, color: '#38bdf8' },
    { key: 'lag', name: '未确认', value: queue?.lag ?? 0, color: '#6366f1' },
    { key: 'retry', name: '等待重试', value: queue?.retry_zset ?? 0, color: '#f59e0b' },
    { key: 'dlq', name: '死信', value: queue?.dlq ?? 0, color: '#ef4444' },
  ]
})

const total = computed(() => legend.value.reduce((sum, item) => sum + item.value, 0))

const segments = computed(() => {
  if (total.value <= 0) return []
  return legend.value
    .filter((item) => item.value > 0)
    .map((item) => ({
      ...item,
      width: `${(item.value / total.value) * 100}%`,
    }))
})
</script>
