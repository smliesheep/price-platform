<template>
  <div class="login-page">
    <div class="login-theme">
      <el-tooltip :content="isDark ? '切换为浅色模式' : '切换为深色模式'" placement="bottom">
        <el-button
          class="icon-button"
          text
          circle
          :aria-label="isDark ? '切换为浅色模式' : '切换为深色模式'"
          @click="toggleTheme"
        >
          <el-icon :size="18">
            <component :is="isDark ? Sunny : Moon" />
          </el-icon>
        </el-button>
      </el-tooltip>
    </div>

    <section class="login-card">
      <div class="login-brand">
        <div class="login-brand__logo">
          <el-icon><TrendCharts /></el-icon>
        </div>
        <div class="login-brand__text">
          <h1>价格监控平台</h1>
          <p>Kubernetes · 云原生 RPA 采集控制台</p>
        </div>
      </div>

      <el-alert
        v-if="noticeText"
        :title="noticeText"
        type="warning"
        show-icon
        class="mb-16"
        @close="noticeText = ''"
      />

      <el-alert
        v-if="errorText"
        :title="errorText"
        type="error"
        show-icon
        :closable="false"
        class="mb-16"
      />

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        size="large"
        class="login-form"
        @submit.prevent="submit"
      >
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            :prefix-icon="User"
            autocomplete="username"
            clearable
          />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            autocomplete="current-password"
            show-password
          />
        </el-form-item>
        <el-button
          type="primary"
          native-type="submit"
          class="login-submit"
          :loading="auth.loggingIn"
        >
          {{ auth.loggingIn ? '正在登录…' : '登 录' }}
        </el-button>
      </el-form>

      <div class="login-foot">
        默认账号 <code>admin</code> / <code>admin123</code><br />
        登录成功后 token 保存在浏览器 localStorage，接口请求自动携带 Bearer 凭证
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { Lock, Moon, Sunny, TrendCharts, User } from '@element-plus/icons-vue'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/http'
import { useTheme } from '@/composables/useTheme'
import { useAuthStore } from '@/stores/auth'
import { errorMessage } from '@/utils/format'
import { consumeFlashMessage, consumeRedirect } from '@/utils/storage'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const { isDark, toggleTheme } = useTheme()

const formRef = ref<FormInstance>()
const form = reactive({
  username: '',
  password: '',
})
const errorText = ref('')
const noticeText = ref('')

onMounted(() => {
  const flash = consumeFlashMessage()
  if (flash) {
    noticeText.value = flash
    ElMessage.warning(flash)
  }
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 位', trigger: 'blur' },
  ],
}

function isSafeRedirect(target: string): boolean {
  return target.startsWith('/') && !target.startsWith('//') && target !== '/login'
}

async function submit(): Promise<void> {
  if (!formRef.value || auth.loggingIn) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  errorText.value = ''
  try {
    await auth.login(form.username.trim(), form.password)
    ElMessage.success('登录成功')
    const fromQuery = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    const target = fromQuery || consumeRedirect()
    await router.replace(isSafeRedirect(target) ? target : '/overview')
  } catch (error) {
    const message =
      error instanceof ApiError && error.status === 401
        ? '用户名或密码错误'
        : errorMessage(error, '登录失败，请稍后重试')
    errorText.value = message
    ElMessage.error(message)
  }
}
</script>
