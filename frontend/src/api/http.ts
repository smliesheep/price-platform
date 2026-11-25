/** axios 实例：统一注入 token / X-Trace-Id、拆封统一响应、401 跳转。 */

import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

import type { ApiEnvelope } from '@/api/types'
import { clearStoredAuth, getToken, setFlashMessage, storeRedirect } from '@/utils/storage'

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** 静默请求：轮询等后台刷新不弹全局错误提示。 */
    silent?: boolean
  }
}

export class ApiError extends Error {
  readonly code: number
  readonly status: number
  readonly traceId?: string

  constructor(message: string, options: { code?: number; status?: number; traceId?: string } = {}) {
    super(message)
    this.name = 'ApiError'
    this.code = options.code ?? -1
    this.status = options.status ?? 0
    this.traceId = options.traceId
  }
}

const recentMessages = new Map<string, number>()

function notify(message: string): void {
  const now = Date.now()
  const last = recentMessages.get(message) ?? 0
  if (now - last < 5000) return
  recentMessages.set(message, now)
  if (recentMessages.size > 60) {
    for (const [key, timestamp] of recentMessages) {
      if (now - timestamp > 60_000) recentMessages.delete(key)
    }
  }
  ElMessage({ message, type: 'error', duration: 4000, grouping: true, showClose: true })
}

function extractMessage(payload: unknown): string | null {
  if (!payload) return null
  if (typeof payload === 'string') return payload
  if (typeof payload !== 'object') return null
  const record = payload as Record<string, unknown>
  if (typeof record.message === 'string' && record.message) return record.message
  const detail = record.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0]
    if (first && typeof first === 'object' && 'msg' in first) {
      const msg = (first as { msg?: unknown }).msg
      if (typeof msg === 'string' && msg) return msg
    }
  }
  return null
}

/** 16 位十六进制 trace id。 */
function randomTraceId(): string {
  const bytes = new Uint8Array(8)
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(bytes)
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256)
    }
  }
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

let redirecting = false

function handleUnauthorized(): void {
  clearStoredAuth()
  if (redirecting) return
  redirecting = true
  if (window.location.pathname !== '/login') {
    storeRedirect(`${window.location.pathname}${window.location.search}`)
    setFlashMessage('登录状态已失效，请重新登录')
    window.location.replace('/login')
  }
}

function isLoginRequest(config?: InternalAxiosRequestConfig): boolean {
  return Boolean(config?.url && config.url.includes('/auth/login'))
}

const client = axios.create({
  baseURL: '/api/v1',
  timeout: 20_000,
  headers: {
    Accept: 'application/json',
  },
})

client.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  config.headers.set('X-Trace-Id', randomTraceId())
  return config
})

client.interceptors.response.use(
  (response) => {
    const payload: unknown = response.data
    if (payload && typeof payload === 'object' && 'code' in payload) {
      const envelope = payload as ApiEnvelope<unknown>
      if (envelope.code !== 0) {
        const error = new ApiError(envelope.message || '请求失败', {
          code: envelope.code,
          status: response.status,
          traceId: envelope.trace_id,
        })
        if (!response.config.silent) notify(error.message)
        return Promise.reject(error)
      }
      return envelope.data as unknown as typeof response
    }
    return response
  },
  (error: AxiosError<unknown>) => {
    const config = error.config
    const status = error.response?.status ?? 0
    let message: string

    if (status === 401) {
      if (isLoginRequest(config)) {
        message = extractMessage(error.response?.data) ?? '用户名或密码错误'
      } else {
        handleUnauthorized()
        return Promise.reject(
          new ApiError('登录状态已失效，请重新登录', { code: 401, status: 401 }),
        )
      }
    } else if (error.code === 'ECONNABORTED' || error.code === 'ETIMEDOUT') {
      message = '请求超时，请稍后重试'
    } else if (!error.response) {
      message = '无法连接到服务，请确认后端已启动'
    } else {
      message = extractMessage(error.response.data) ?? `请求失败（HTTP ${status}）`
    }

    if (!config?.silent) notify(message)
    const traceId = error.response?.headers?.['x-trace-id']
    return Promise.reject(
      new ApiError(message, {
        status,
        code: status,
        traceId: typeof traceId === 'string' ? traceId : undefined,
      }),
    )
  },
)

export type RequestConfig = AxiosRequestConfig

export function get<T>(url: string, config?: RequestConfig): Promise<T> {
  return client.get(url, config).then((response) => response as unknown as T)
}

export function post<T>(url: string, data?: unknown, config?: RequestConfig): Promise<T> {
  return client.post(url, data, config).then((response) => response as unknown as T)
}

export function patch<T>(url: string, data?: unknown, config?: RequestConfig): Promise<T> {
  return client.patch(url, data, config).then((response) => response as unknown as T)
}

export function del<T = void>(url: string, config?: RequestConfig): Promise<T> {
  return client.delete(url, config).then((response) => response as unknown as T)
}

/** 去掉空字符串 / undefined / null 查询参数，避免后端 422。 */
export function cleanParams(params: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    result[key] = value
  }
  return result
}
