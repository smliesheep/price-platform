/** localStorage 键名与读写封装（请求层、路由守卫、Pinia 共用）。 */

export const TOKEN_KEY = 'price_monitor_token'
export const USERNAME_KEY = 'price_monitor_username'
export const REDIRECT_KEY = 'price_monitor_redirect'
export const THEME_KEY = 'price_monitor_theme'
export const FLASH_KEY = 'price_monitor_flash'

export function getToken(): string {
  try {
    return window.localStorage.getItem(TOKEN_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token)
  } catch {
    /* 隐私模式下 localStorage 不可用时忽略 */
  }
}

export function getStoredUsername(): string {
  try {
    return window.localStorage.getItem(USERNAME_KEY) ?? ''
  } catch {
    return ''
  }
}

export function setStoredUsername(username: string): void {
  try {
    if (username) window.localStorage.setItem(USERNAME_KEY, username)
  } catch {
    /* ignore */
  }
}

export function clearStoredAuth(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY)
    window.localStorage.removeItem(USERNAME_KEY)
  } catch {
    /* ignore */
  }
}

export function getStoredTheme(): 'dark' | 'light' | null {
  try {
    const value = window.localStorage.getItem(THEME_KEY)
    return value === 'dark' || value === 'light' ? value : null
  } catch {
    return null
  }
}

export function setStoredTheme(theme: 'dark' | 'light'): void {
  try {
    window.localStorage.setItem(THEME_KEY, theme)
  } catch {
    /* ignore */
  }
}

export function consumeRedirect(): string {
  try {
    const target = window.sessionStorage.getItem(REDIRECT_KEY) ?? ''
    window.sessionStorage.removeItem(REDIRECT_KEY)
    return target
  } catch {
    return ''
  }
}

export function storeRedirect(path: string): void {
  try {
    window.sessionStorage.setItem(REDIRECT_KEY, path)
  } catch {
    /* ignore */
  }
}

/** 跨页面跳转的一次性提示（如登录失效）。 */
export function setFlashMessage(message: string): void {
  try {
    window.sessionStorage.setItem(FLASH_KEY, message)
  } catch {
    /* ignore */
  }
}

export function consumeFlashMessage(): string {
  try {
    const message = window.sessionStorage.getItem(FLASH_KEY) ?? ''
    window.sessionStorage.removeItem(FLASH_KEY)
    return message
  } catch {
    return ''
  }
}
