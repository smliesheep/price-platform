import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

import { getToken } from '@/utils/storage'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: () => import('@/components/AppLayout.vue'),
    redirect: '/overview',
    children: [
      {
        path: 'overview',
        name: 'overview',
        component: () => import('@/views/OverviewView.vue'),
        meta: { title: '概览' },
      },
      {
        path: 'products',
        name: 'products',
        component: () => import('@/views/ProductsView.vue'),
        meta: { title: '商品' },
      },
      {
        path: 'products/:id(\\d+)',
        name: 'product-detail',
        component: () => import('@/views/ProductDetailView.vue'),
        meta: { title: '商品详情', activeMenu: '/products' },
      },
      {
        path: 'tasks',
        name: 'tasks',
        component: () => import('@/views/TasksView.vue'),
        meta: { title: '任务' },
      },
      {
        path: 'runs',
        name: 'runs',
        component: () => import('@/views/RunsView.vue'),
        meta: { title: '执行记录' },
      },
      {
        path: 'system',
        name: 'system',
        component: () => import('@/views/SystemView.vue'),
        meta: { title: '系统状态' },
      },
    ],
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/overview',
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  const token = getToken()
  if (!to.meta.public && !token) {
    return {
      path: '/login',
      query: to.fullPath && to.fullPath !== '/overview' ? { redirect: to.fullPath } : {},
    }
  }
  if (to.path === '/login' && token) {
    return { path: '/overview' }
  }
  return true
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : ''
  document.title = title ? `${title} · 价格监控平台` : '价格监控平台'
})

export default router
