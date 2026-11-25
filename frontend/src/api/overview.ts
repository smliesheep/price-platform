import { get, type RequestConfig } from '@/api/http'
import type { Overview } from '@/api/types'

export function getOverview(config?: RequestConfig): Promise<Overview> {
  return get<Overview>('/overview', config)
}
