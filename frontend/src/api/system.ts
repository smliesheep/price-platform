import { get, type RequestConfig } from '@/api/http'
import type { QueueInfo, VersionInfo, WorkersResult } from '@/api/types'

export function getWorkers(config?: RequestConfig): Promise<WorkersResult> {
  return get<WorkersResult>('/workers', config)
}

export function getQueue(config?: RequestConfig): Promise<QueueInfo> {
  return get<QueueInfo>('/system/queue', config)
}

export function getVersion(config?: RequestConfig): Promise<VersionInfo> {
  return get<VersionInfo>('/system/version', config)
}
