import { cleanParams, get, patch, post, type RequestConfig } from '@/api/http'
import type {
  PageResult,
  RunTriggerResult,
  TaskInfo,
  TaskItem,
  TaskQuery,
  UpdateTaskPayload,
} from '@/api/types'

export function getTasks(
  params: TaskQuery = {},
  config?: RequestConfig,
): Promise<PageResult<TaskItem>> {
  return get<PageResult<TaskItem>>('/tasks', {
    ...config,
    params: cleanParams({ ...params }),
  })
}

export function getTask(id: number, config?: RequestConfig): Promise<TaskItem> {
  return get<TaskItem>(`/tasks/${id}`, config)
}

export function updateTask(
  id: number,
  payload: UpdateTaskPayload,
  config?: RequestConfig,
): Promise<TaskInfo> {
  return patch<TaskInfo>(`/tasks/${id}`, payload, config)
}

export function runTask(id: number, config?: RequestConfig): Promise<RunTriggerResult> {
  return post<RunTriggerResult>(`/tasks/${id}/run`, undefined, config)
}

export function pauseTask(id: number, config?: RequestConfig): Promise<TaskInfo> {
  return post<TaskInfo>(`/tasks/${id}/pause`, undefined, config)
}

export function resumeTask(id: number, config?: RequestConfig): Promise<TaskInfo> {
  return post<TaskInfo>(`/tasks/${id}/resume`, undefined, config)
}
