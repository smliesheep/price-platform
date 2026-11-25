import { ref } from 'vue'

import { getStoredTheme, setStoredTheme } from '@/utils/storage'

const isDark = ref(false)
let initialized = false

function applyTheme(dark: boolean): void {
  isDark.value = dark
  if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('dark', dark)
    document.documentElement.style.colorScheme = dark ? 'dark' : 'light'
  }
  setStoredTheme(dark ? 'dark' : 'light')
}

/** 应用启动时调用一次：默认浅色，读取本地偏好。 */
export function initTheme(): void {
  if (initialized) return
  initialized = true
  const saved = getStoredTheme()
  applyTheme(saved === 'dark')
}

export function useTheme() {
  return {
    isDark,
    setTheme: applyTheme,
    toggleTheme: () => applyTheme(!isDark.value),
  }
}
