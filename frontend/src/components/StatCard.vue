<template>
  <div class="stat-card">
    <div v-if="icon" class="stat-card__icon" :class="`tone-${tone}`">
      <el-icon><component :is="icon" /></el-icon>
    </div>
    <div class="stat-card__content">
      <div class="stat-card__label">{{ label }}</div>
      <el-skeleton v-if="loading" :rows="1" animated class="stat-card__skeleton" />
      <template v-else>
        <div class="stat-card__value">
          {{ value ?? '—' }}
          <small v-if="unit">{{ unit }}</small>
        </div>
        <div v-if="hint" class="stat-card__hint">{{ hint }}</div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

withDefaults(
  defineProps<{
    label: string
    value?: string | number
    unit?: string
    hint?: string
    tone?: 'primary' | 'success' | 'warning' | 'danger'
    icon?: Component
    loading?: boolean
  }>(),
  {
    value: undefined,
    unit: '',
    hint: '',
    tone: 'primary',
    icon: undefined,
    loading: false,
  },
)
</script>
