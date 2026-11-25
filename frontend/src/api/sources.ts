import { get, type RequestConfig } from '@/api/http'
import type { Source } from '@/api/types'

export function getSources(config?: RequestConfig): Promise<Source[]> {
  return get<Source[]>('/sources', config)
}
