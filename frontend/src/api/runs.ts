import { cleanParams, get, type RequestConfig } from '@/api/http'
import type { PageResult, Run, RunDetail, RunQuery } from '@/api/types'

export function getRuns(params: RunQuery = {}, config?: RequestConfig): Promise<PageResult<Run>> {
  return get<PageResult<Run>>('/runs', {
    ...config,
    params: cleanParams({ ...params }),
  })
}

export function getRun(id: number, config?: RequestConfig): Promise<RunDetail> {
  return get<RunDetail>(`/runs/${id}`, config)
}
