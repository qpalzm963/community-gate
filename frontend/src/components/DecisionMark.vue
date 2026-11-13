<template>
  <span class="decision-mark" :class="tone">
    <el-icon class="mark-icon"><component :is="icon" /></el-icon>
    <span>{{ DECISION_LABEL[decision] || decision }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheck, CircleX, Clock } from 'lucide-vue-next'
import { DECISION_LABEL } from '../api'

const props = defineProps<{ decision: string }>()

const tone = computed(() => {
  if (props.decision === 'AUTO_ALLOW' || props.decision === 'MANUAL_ALLOW') return 'allow'
  if (props.decision === 'DENY') return 'deny'
  return 'pending'
})

const icon = computed(() => ({ allow: CircleCheck, deny: CircleX, pending: Clock })[tone.value])
</script>

<style scoped>
/* 放行 / 待處理 / 拒絕：左側細色條 + 圖示，不用整塊高飽和底色 */
.decision-mark {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 1px 10px 1px 8px;
  border-left: 3px solid currentColor;
  border-radius: 0 var(--cg-radius-sm) var(--cg-radius-sm) 0;
  font-size: var(--cg-text-sm);
  font-weight: 500;
  white-space: nowrap;
  line-height: 1.7;
}
.mark-icon {
  font-size: 14px;
}
.allow {
  color: var(--cg-success-text);
  background: color-mix(in srgb, var(--cg-success) 8%, transparent);
}
.deny {
  color: var(--cg-danger-text);
  background: color-mix(in srgb, var(--cg-danger) 8%, transparent);
}
.pending {
  color: var(--cg-warning-text);
  background: color-mix(in srgb, var(--cg-warning) 10%, transparent);
}
</style>
