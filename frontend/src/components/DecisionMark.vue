<template>
  <span class="decision-mark" :class="tone">
    <span>{{ DECISION_LABEL[decision] || decision }}</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { DECISION_LABEL } from '../api'

const props = defineProps<{ decision: string }>()

const tone = computed(() => {
  if (props.decision === 'AUTO_ALLOW' || props.decision === 'MANUAL_ALLOW') return 'allow'
  if (props.decision === 'DENY') return 'deny'
  return 'pending'
})
</script>

<style scoped>
/* 放行 / 待處理 / 拒絕：淡底膠囊 + 前置圓點 */
.decision-mark {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 9px;
  border-radius: var(--cg-radius-pill);
  font-size: var(--cg-text-xs);
  font-weight: 600;
  white-space: nowrap;
  line-height: 1.5;
}
.decision-mark::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.allow {
  color: var(--cg-success-text);
  background: color-mix(in srgb, var(--cg-success) 12%, var(--cg-surface));
}
.deny {
  color: var(--cg-danger-text);
  background: color-mix(in srgb, var(--cg-danger) 12%, var(--cg-surface));
}
.pending {
  color: var(--cg-warning-text);
  background: color-mix(in srgb, var(--cg-warning) 14%, var(--cg-surface));
}
</style>
