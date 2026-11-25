import { get, post, type RequestConfig } from '@/api/http'
import type { LoginResult, MeResult } from '@/api/types'

export function login(
  payload: { username: string; password: string },
  config?: RequestConfig,
): Promise<LoginResult> {
  return post<LoginResult>('/auth/login', payload, config)
}

export function getMe(config?: RequestConfig): Promise<MeResult> {
  return get<MeResult>('/auth/me', config)
}
