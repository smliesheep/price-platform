<template>
  <div class="app-shell" :class="{ 'is-collapsed': collapsed }">
    <aside class="app-sidebar">
      <div class="brand">
        <div class="brand__logo">
          <el-icon><TrendCharts /></el-icon>
        </div>
        <div class="brand__text">
          <strong>价格监控</strong>
          <span>K8S · CLOUD RPA</span>
        </div>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="collapsed"
        :collapse-transition="false"
        class="app-menu"
        router
      >
        <el-menu-item v-for="item in menuItems" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-foot">
        <div><span class="dot" />云原生采集平台</div>
        <div>v0.1.0 · Console</div>
      </div>
    </aside>

    <div class="app-main">
      <header class="app-topbar">
        <div class="topbar-left">
          <el-button
            class="icon-button"
            text
            circle
            :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
            @click="collapsed = !collapsed"
          >
            <el-icon :size="18">
              <component :is="collapsed ? Expand : Fold" />
            </el-icon>
          </el-button>
          <div class="topbar-heading">
            <h1>{{ pageTitle }}</h1>
            <span>价格监控 / {{ pageTitle }}</span>
          </div>
        </div>

        <div class="topbar-right">
          <el-tag v-if="auth.authDisabled" type="warning" effect="plain" size="small">
            鉴权已关闭
          </el-tag>
          <el-tooltip :content="isDark ? '切换为浅色模式' : '切换为深色模式'" placement="bottom">
            <el-button
              class="icon-button"
              text
              circle
              :aria-label="isDark ? '切换为浅色模式' : '切换为深色模式'"
              @click="toggleTheme"
            >
              <el-icon :size="17">
                <component :is="isDark ? Sunny : Moon" />
              </el-icon>
            </el-button>
          </el-tooltip>

          <el-dropdown trigger="click" @command="handleCommand">
            <span class="user-chip">
              <el-avatar :size="26" class="user-avatar">{{ auth.initial }}</el-avatar>
              <span class="user-chip__name">{{ auth.displayName }}</span>
              <el-icon :size="12"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item disabled>
                  <el-icon><User /></el-icon>
                  {{ auth.displayName }}
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>
                  退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <main class="app-content">
        <router-view v-slot="{ Component }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  ArrowDown,
  Expand,
  Fold,
  Goods,
  Monitor,
  Moon,
  Odometer,
  Sunny,
  SwitchButton,
  Tickets,
  Timer,
  TrendCharts,
  User,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, markRaw, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useTheme } from '@/composables/useTheme'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { isDark, toggleTheme } = useTheme()

const collapsed = ref(typeof window !== 'undefined' ? window.innerWidth < 1100 : false)

const menuItems = [
  { path: '/overview', title: '概览', icon: markRaw(Odometer) },
  { path: '/products', title: '商品', icon: markRaw(Goods) },
  { path: '/tasks', title: '任务', icon: markRaw(Timer) },
  { path: '/runs', title: '执行记录', icon: markRaw(Tickets) },
  { path: '/system', title: '系统状态', icon: markRaw(Monitor) },
]

const activeMenu = computed(() => {
  const configured = route.meta.activeMenu
  if (typeof configured === 'string') return configured
  return route.path
})

const pageTitle = computed(() => (typeof route.meta.title === 'string' ? route.meta.title : ''))

onMounted(() => {
  if (auth.token) void auth.fetchMe()
})

async function handleCommand(command: string | number | object): Promise<void> {
  if (command !== 'logout') return
  try {
    await ElMessageBox.confirm('确定退出当前账号吗？', '退出登录', {
      confirmButtonText: '退出登录',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  auth.logout()
  ElMessage.success('已退出登录')
  await router.replace('/login')
}
</script>

<style scoped>
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(4px);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-3px);
}
</style>
