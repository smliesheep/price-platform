import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getMe, login as loginRequest } from '@/api/auth'
import type { LoginResult } from '@/api/types'
import {
  clearStoredAuth,
  getStoredUsername,
  getToken,
  setStoredUsername,
  setToken,
} from '@/utils/storage'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(getToken())
  const username = ref(getStoredUsername())
  const authDisabled = ref(false)
  const loggingIn = ref(false)
  const meLoading = ref(false)

  const isAuthenticated = computed(() => Boolean(token.value))
  const displayName = computed(() => username.value || '未登录')
  const initial = computed(() => (username.value ? username.value.slice(0, 1).toUpperCase() : 'U'))

  async function login(account: string, password: string): Promise<LoginResult> {
    loggingIn.value = true
    try {
      const result = await loginRequest({ username: account, password }, { silent: true })
      token.value = result.access_token
      username.value = result.username || account
      setToken(result.access_token)
      setStoredUsername(username.value)
      return result
    } finally {
      loggingIn.value = false
    }
  }

  async function fetchMe(): Promise<void> {
    if (!token.value) return
    meLoading.value = true
    try {
      const result = await getMe({ silent: true })
      username.value = result.username
      authDisabled.value = result.auth_disabled
      setStoredUsername(result.username)
    } catch {
      // 401 已由请求层清 token 并跳转，其余错误静默，不阻塞布局
    } finally {
      meLoading.value = false
    }
  }

  function logout(): void {
    token.value = ''
    username.value = ''
    authDisabled.value = false
    clearStoredAuth()
  }

  return {
    token,
    username,
    authDisabled,
    loggingIn,
    meLoading,
    isAuthenticated,
    displayName,
    initial,
    login,
    fetchMe,
    logout,
  }
})
