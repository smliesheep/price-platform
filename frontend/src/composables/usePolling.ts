import { onBeforeUnmount, onMounted, ref } from 'vue'

type PollingTask = () => Promise<unknown> | unknown

export interface UsePollingOptions {
  /** 是否挂载后立即执行一次（页面通常自行做首次加载，默认关闭）。 */
  immediate?: boolean
}

/**
 * 轮询组合式函数：
 * - 页面隐藏（visibilityState === 'hidden'）时暂停定时器；
 * - 重新可见时立即刷新并恢复定时器；
 * - 同一时间最多一个请求在途，组件卸载时清理全部监听与定时器。
 */
export function usePolling(fn: PollingTask, intervalMs: number, options: UsePollingOptions = {}) {
  const running = ref(false)
  const active = ref(false)
  let timer: number | null = null

  const clearTimer = () => {
    if (timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
  }

  const startTimer = () => {
    clearTimer()
    if (!active.value) return
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
    timer = window.setInterval(() => {
      void run()
    }, Math.max(1000, intervalMs))
  }

  const run = async (): Promise<void> => {
    if (!active.value || running.value) return
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
    running.value = true
    try {
      await fn()
    } catch {
      // 页面自行维护错误状态，这里只保证轮询不中断
    } finally {
      running.value = false
    }
  }

  const handleVisibilityChange = () => {
    if (document.visibilityState === 'visible') {
      void run()
      startTimer()
    } else {
      clearTimer()
    }
  }

  onMounted(() => {
    active.value = true
    document.addEventListener('visibilitychange', handleVisibilityChange)
    startTimer()
    if (options.immediate) void run()
  })

  onBeforeUnmount(() => {
    active.value = false
    clearTimer()
    document.removeEventListener('visibilitychange', handleVisibilityChange)
  })

  return {
    running,
    refresh: run,
    start: startTimer,
    stop: clearTimer,
  }
}
