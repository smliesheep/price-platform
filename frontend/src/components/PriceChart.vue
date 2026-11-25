<template>
  <div class="price-chart">
    <div v-if="stats" class="chart-stats">
      <div class="chart-stat">
        <span class="chart-stat__label">最新价</span>
        <span class="chart-stat__value">{{ formatMoney(stats.latest, currency) }}</span>
      </div>
      <div class="chart-stat">
        <span class="chart-stat__label">区间最高</span>
        <span class="chart-stat__value">{{ formatMoney(stats.max, currency) }}</span>
      </div>
      <div class="chart-stat">
        <span class="chart-stat__label">区间最低</span>
        <span class="chart-stat__value">{{ formatMoney(stats.min, currency) }}</span>
      </div>
      <div class="chart-stat">
        <span class="chart-stat__label">样本点</span>
        <span class="chart-stat__value">{{ stats.count }}</span>
      </div>
      <div v-if="targetPrice !== null && targetPrice !== undefined" class="chart-stat">
        <span class="chart-stat__label">目标价</span>
        <span class="chart-stat__value text-warning">{{ formatMoney(targetPrice, currency) }}</span>
      </div>
    </div>

    <div
      v-loading="loading"
      class="chart-wrap"
      element-loading-text="正在加载价格数据…"
      element-loading-background="transparent"
    >
      <div ref="chartEl" class="chart-canvas" />

      <div v-if="!loading && error" class="chart-overlay">
        <el-icon :size="26" class="text-danger"><WarningFilled /></el-icon>
        <div class="chart-overlay__text">{{ error }}</div>
        <el-button size="small" @click="emit('retry')">重试</el-button>
      </div>

      <div v-else-if="!loading && points.length === 0" class="chart-overlay">
        <el-empty :image-size="74" description="当前时间范围暂无价格数据" />
      </div>
    </div>

    <div v-if="downsampled" class="chart-note">
      数据量较大，后端已截断为最近 2000 条采样点；可切换 1h / 1d 聚合粒度查看长期趋势。
    </div>
    <div v-else-if="points.length > 0" class="chart-note">
      统计区间：{{ formatDateTime(rangeFrom) }} ~ {{ formatDateTime(rangeTo) }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { WarningFilled } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import type { EChartsOption } from 'echarts'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { PriceGranularity, PricePoint } from '@/api/types'
import { useTheme } from '@/composables/useTheme'
import {
  formatChartTime,
  formatDateTime,
  formatMoney,
  currencySymbol,
} from '@/utils/format'

const props = withDefaults(
  defineProps<{
    points: PricePoint[]
    targetPrice?: number | null
    granularity?: PriceGranularity
    currency?: string
    loading?: boolean
    error?: string
    downsampled?: boolean
    rangeFrom?: string
    rangeTo?: string
  }>(),
  {
    targetPrice: null,
    granularity: 'raw',
    currency: 'CNY',
    loading: false,
    error: '',
    downsampled: false,
    rangeFrom: '',
    rangeTo: '',
  },
)

const emit = defineEmits<{ (event: 'retry'): void }>()

const { isDark } = useTheme()
const chartEl = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null
let observer: ResizeObserver | null = null

const targetPrice = computed(() => props.targetPrice)

const stats = computed(() => {
  if (props.points.length === 0) return null
  const prices = props.points.map((point) => point.price)
  return {
    latest: prices[prices.length - 1],
    max: Math.max(...prices),
    min: Math.min(...prices),
    count: prices.length,
  }
})

function buildOption(): EChartsOption {
  const dark = isDark.value
  const axisColor = dark ? '#334155' : '#e2e8f0'
  const textColor = dark ? '#94a3b8' : '#64748b'
  const gridColor = dark ? 'rgba(148, 163, 184, 0.16)' : '#eef2f7'
  const symbol = currencySymbol(props.currency)
  const labels = props.points.map((point) => formatChartTime(point.t, props.granularity))
  const prices = props.points.map((point) => point.price)
  const showSymbol = props.points.length <= 60

  const option: EChartsOption = {
    animationDuration: 400,
    backgroundColor: 'transparent',
    grid: { left: 12, right: 44, top: 34, bottom: 10, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: dark ? 'rgba(17, 26, 46, 0.97)' : 'rgba(255, 255, 255, 0.98)',
      borderColor: dark ? '#2d3e5c' : '#e4eaf3',
      borderWidth: 1,
      padding: 10,
      textStyle: { color: dark ? '#e6edf8' : '#182234', fontSize: 12 },
      extraCssText: 'box-shadow: 0 8px 24px rgba(15, 23, 42, 0.16); border-radius: 8px;',
      formatter: (params: unknown) => {
        const list = Array.isArray(params) ? params : [params]
        const first = list[0] as { dataIndex?: number } | undefined
        const index = first?.dataIndex ?? 0
        const point = props.points[index]
        if (!point) return ''
        const stockText =
          point.in_stock === null ? '库存未知' : point.in_stock ? '有货' : '缺货'
        const stockColor =
          point.in_stock === null ? textColor : point.in_stock ? '#16a34a' : '#dc2626'
        return [
          `<div style="margin-bottom:6px;color:${textColor};font-size:11px">${formatDateTime(point.t)}</div>`,
          `<div style="display:flex;align-items:center;gap:8px;font-size:13px">`,
          `<span style="width:8px;height:8px;border-radius:50%;background:#3b82f6;display:inline-block"></span>`,
          `<span>价格</span>`,
          `<b style="margin-left:auto;font-variant-numeric:tabular-nums">${formatMoney(point.price, props.currency)}</b>`,
          `</div>`,
          `<div style="margin-top:4px;font-size:11px;color:${textColor}">库存：<span style="color:${stockColor}">${stockText}</span></div>`,
        ].join('')
      },
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: labels,
      axisLine: { lineStyle: { color: axisColor } },
      axisTick: { show: false },
      axisLabel: { color: textColor, fontSize: 11, hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: textColor,
        fontSize: 11,
        formatter: (value: number) => `${symbol}${Number(value).toFixed(2)}`,
      },
      splitLine: { lineStyle: { color: gridColor, type: 'dashed' } },
    },
    series: [
      {
        name: '价格',
        type: 'line',
        data: prices,
        smooth: true,
        showSymbol,
        symbol: 'circle',
        symbolSize: 6,
        lineStyle: { width: 2.2, color: '#3b82f6' },
        itemStyle: {
          color: '#3b82f6',
          borderColor: dark ? '#111a2e' : '#ffffff',
          borderWidth: 1,
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(59, 130, 246, 0.28)' },
            { offset: 1, color: 'rgba(59, 130, 246, 0.02)' },
          ]),
        },
        emphasis: { focus: 'series' },
        markLine:
          props.targetPrice !== null && props.targetPrice !== undefined
            ? {
                silent: true,
                symbol: 'none',
                lineStyle: { color: '#f59e0b', type: 'dashed', width: 1.5 },
                label: {
                  show: true,
                  position: 'insideEndTop',
                  color: '#f59e0b',
                  fontSize: 11,
                  formatter: `目标价 ${formatMoney(props.targetPrice, props.currency)}`,
                },
                data: [{ yAxis: props.targetPrice }],
              }
            : undefined,
      },
    ],
  }

  return option
}

function render(): void {
  if (!chartEl.value) return
  if (props.points.length === 0) {
    chart?.clear()
    return
  }
  if (!chart) {
    chart = echarts.init(chartEl.value)
  }
  chart.setOption(buildOption(), true)
}

function resize(): void {
  chart?.resize()
}

onMounted(() => {
  void nextTick(() => {
    render()
    if (chartEl.value && typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => resize())
      observer.observe(chartEl.value)
    }
    window.addEventListener('resize', resize)
  })
})

watch(
  () => [props.points, props.targetPrice, props.granularity, isDark.value] as const,
  async () => {
    await nextTick()
    render()
  },
)

onBeforeUnmount(() => {
  observer?.disconnect()
  observer = null
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
</script>
