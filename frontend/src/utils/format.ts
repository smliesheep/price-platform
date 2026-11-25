/** 统一格式化工具：金额、时间、间隔、耗时等。 */

import type { PriceGranularity } from '@/api/types'

const pad = (value: number): string => String(value).padStart(2, '0')

/** 兼容后端带时区的 ISO 字符串；无时区信息时按 UTC 处理。 */
export function parseDate(value?: string | null): Date | null {
  if (!value) return null
  const hasTimezone = /(?:[zZ]|[+-]\d{2}:?\d{2})$/.test(value)
  const normalized = hasTimezone ? value : `${value}Z`
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

/** 本地时区 YYYY-MM-DD HH:mm:ss。 */
export function formatDateTime(value?: string | null, fallback = '—'): string {
  const date = parseDate(value)
  if (!date) return fallback
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

/** 本地时区 YYYY-MM-DD。 */
export function formatDate(value?: string | null, fallback = '—'): string {
  const date = parseDate(value)
  if (!date) return fallback
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** 图轴用的短时间。 */
export function formatChartTime(value?: string | null, granularity: PriceGranularity = 'raw'): string {
  const date = parseDate(value)
  if (!date) return ''
  const monthDay = `${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
  if (granularity === '1d') return monthDay
  return `${monthDay} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function currencySymbol(currency?: string | null): string {
  switch ((currency ?? 'CNY').toUpperCase()) {
    case 'CNY':
    case 'RMB':
      return '¥'
    case 'USD':
      return '$'
    case 'EUR':
      return '€'
    case 'GBP':
      return '£'
    case 'JPY':
      return '¥'
    default:
      return ''
  }
}

/** 金额固定两位小数，非法值显示占位符。 */
export function formatMoney(value?: number | null, currency = 'CNY'): string {
  if (value === null || value === undefined) return '—'
  const amount = Number(value)
  if (!Number.isFinite(amount)) return '—'
  return `${currencySymbol(currency)}${amount.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

export function formatNumber(value?: number | null, fallback = '—'): string {
  if (value === null || value === undefined) return fallback
  const amount = Number(value)
  if (!Number.isFinite(amount)) return fallback
  return amount.toLocaleString('zh-CN')
}

/** 后端 success_rate 为 0~1 的小数。 */
export function formatPercent(value?: number | null, fallback = '—'): string {
  if (value === null || value === undefined) return fallback
  const amount = Number(value)
  if (!Number.isFinite(amount)) return fallback
  return `${(amount * 100).toFixed(1)}%`
}

export function formatInterval(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return '—'
  const value = Math.max(0, Math.floor(Number(seconds)))
  if (!Number.isFinite(value)) return '—'
  if (value < 60) return `${value} 秒`
  if (value < 3600) {
    const minutes = Math.floor(value / 60)
    const rest = value % 60
    return rest === 0 ? `${minutes} 分钟` : `${minutes} 分 ${rest} 秒`
  }
  if (value < 86400) {
    const hours = Math.floor(value / 3600)
    const minutes = Math.floor((value % 3600) / 60)
    return minutes === 0 ? `${hours} 小时` : `${hours} 小时 ${minutes} 分`
  }
  const days = Math.floor(value / 86400)
  const hours = Math.floor((value % 86400) / 3600)
  return hours === 0 ? `${days} 天` : `${days} 天 ${hours} 小时`
}

export function formatDuration(ms?: number | null): string {
  if (ms === null || ms === undefined) return '—'
  const value = Number(ms)
  if (!Number.isFinite(value)) return '—'
  if (value < 1000) return `${Math.round(value)} ms`
  if (value < 60_000) return `${(value / 1000).toFixed(2)} s`
  const minutes = Math.floor(value / 60_000)
  const seconds = Math.round((value % 60_000) / 1000)
  return `${minutes} 分 ${seconds} 秒`
}

export function formatAge(seconds?: number | null): string {
  if (seconds === null || seconds === undefined) return '—'
  const value = Math.max(0, Math.floor(Number(seconds)))
  if (!Number.isFinite(value)) return '—'
  if (value < 60) return `${value} 秒前`
  if (value < 3600) return `${Math.floor(value / 60)} 分钟前`
  if (value < 86400) return `${Math.floor(value / 3600)} 小时前`
  return `${Math.floor(value / 86400)} 天前`
}

export function truncate(value?: string | null, max = 40): string {
  if (!value) return '—'
  return value.length > max ? `${value.slice(0, max)}…` : value
}

export function errorMessage(error: unknown, fallback = '请求失败，请稍后重试'): string {
  if (error instanceof Error && error.message) return error.message
  if (typeof error === 'string' && error) return error
  return fallback
}

/** 复制文本，失败时回退到 textarea + execCommand（无外网依赖）。 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (!text) return false
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* 继续尝试回退方案 */
  }
  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    textarea.style.pointerEvents = 'none'
    document.body.appendChild(textarea)
    textarea.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(textarea)
    return ok
  } catch {
    return false
  }
}
