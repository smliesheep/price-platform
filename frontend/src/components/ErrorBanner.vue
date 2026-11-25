<template>
  <div class="error-banner" role="alert">
    <el-icon class="error-banner__icon"><WarningFilled /></el-icon>
    <div class="error-banner__body">
      <strong>{{ title }}</strong>
      <p>{{ message }}</p>
    </div>
    <el-button v-if="retryable" size="small" type="danger" plain @click="emit('retry')">
      重试
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { WarningFilled } from '@element-plus/icons-vue'

withDefaults(
  defineProps<{
    message?: string
    title?: string
    retryable?: boolean
  }>(),
  {
    message: '请检查网络或后端服务后重试',
    title: '加载失败',
    retryable: true,
  },
)

const emit = defineEmits<{ (event: 'retry'): void }>()
</script>
