/** 后端统一响应与业务实体类型定义。 */

export interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
  trace_id: string
}

export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface LoginResult {
  access_token: string
  token_type: string
  expires_in: number
  username: string
}

export interface MeResult {
  username: string
  auth_disabled: boolean
}

export interface QueueStats {
  length: number
  pending: number
  lag: number
  dlq: number
  retry_zset: number
}

export interface TopError {
  error_type: string
  count: number
}

export interface Overview {
  prices_24h: number
  runs_24h: number
  success_24h: number
  success_rate: number
  products_enabled: number
  products_total: number
  inflight: number
  workers_online: number
  queue: QueueStats
  top_errors: TopError[]
  generated_at: string
}

export type TaskStatus = 'active' | 'paused' | 'archived'
export type ScheduleType = 'interval' | 'cron'

export interface TaskInfo {
  id: number
  product_id: number
  schedule_type: ScheduleType
  interval_sec: number
  cron_expr: string | null
  priority: number
  status: TaskStatus
  next_run_at: string | null
  last_run_at: string | null
  max_retry: number
  timeout_sec: number
}

export interface TaskItem extends TaskInfo {
  product_title: string | null
  product_enabled?: boolean
}

export interface Product {
  id: number
  source_id: number
  source_name: string | null
  external_id: string
  title: string
  url: string
  category: string | null
  target_price: number | null
  selector_version: string
  enabled: boolean
  current_price: number | null
  last_collected_at: string | null
  last_status: string | null
  created_at: string | null
  updated_at?: string | null
  task?: TaskInfo | null
}

export type RunStatus =
  | 'queued'
  | 'running'
  | 'success'
  | 'failed'
  | 'timeout'
  | 'canceled'
  | 'retry_wait'

export interface Run {
  id: number
  task_id: number
  product_id: number
  product_title: string | null
  slot_at: string | null
  attempt: number
  status: RunStatus
  worker_id: string | null
  trace_id: string | null
  queued_at: string | null
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  http_status: number | null
  error_type: string | null
  error_msg: string | null
}

export interface RunDetail extends Run {
  product_url: string | null
}

export type PriceGranularity = 'raw' | '1h' | '1d'

export interface PricePoint {
  t: string
  price: number
  in_stock: boolean | null
}

export interface PriceSeries {
  granularity: PriceGranularity
  currency: string
  target_price: number | null
  from: string
  to: string
  downsampled: boolean
  points: PricePoint[]
}

export interface RunTriggerResult {
  run_id: number
  slot_at: string
  task_id: number
}

export interface WorkerInfo {
  id: string
  node: string
  version: string | null
  inflight: number
  last_heartbeat: string | null
  heartbeat_age_sec: number | null
  online: boolean
}

export interface WorkersResult {
  items: WorkerInfo[]
  online: number
}

export interface QueueConsumer {
  name: string
  pending: number
  idle_ms: number
}

export interface QueueInfo extends QueueStats {
  stream: string
  group: string
  consumers: QueueConsumer[]
}

export interface VersionInfo {
  version: string
  stream: string
  group: string
  scheduler_tick_sec: number
  retry_delay_sec: number
  worker_concurrency: number
}

export interface Source {
  id: number
  name: string
  base_url: string
  adapter: string
  rate_limit_per_min: number
  proxy_group: string | null
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export interface ProductQuery {
  q?: string
  source_id?: number
  enabled?: boolean
  page?: number
  page_size?: number
}

export interface CreateProductPayload {
  source_id: number
  url: string
  title?: string
  category?: string
  target_price?: number
  interval_sec?: number
  selector_version?: string
  external_id?: string
}

export interface UpdateProductPayload {
  title?: string
  category?: string
  target_price?: number | null
  selector_version?: string
  url?: string
}

export interface PriceQuery {
  from?: string
  to?: string
  granularity?: PriceGranularity
}

export interface RunQuery {
  status?: string
  error_type?: string
  worker_id?: string
  product_id?: number
  from?: string
  to?: string
  page?: number
  page_size?: number
}

export interface TaskQuery {
  status?: string
  page?: number
  page_size?: number
}

export interface UpdateTaskPayload {
  schedule_type?: ScheduleType
  interval_sec?: number
  cron_expr?: string | null
  priority?: number
  max_retry?: number
  timeout_sec?: number
}
