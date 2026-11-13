<template>
  <div class="empty-state">
    <!-- 線條插圖：社區大門與柵欄 -->
    <svg width="120" height="76" viewBox="0 0 120 76" aria-hidden="true" class="empty-art">
      <path d="M8 70 H112" class="ground" />
      <rect x="16" y="22" width="14" height="48" rx="2" class="post" />
      <rect x="90" y="22" width="14" height="48" rx="2" class="post" />
      <path d="M30 34 H90" class="bar" />
      <path d="M30 34 L38 28 M46 34 L54 28 M62 34 L70 28 M78 34 L86 28" class="bar-dash" />
      <circle cx="23" cy="16" r="4" class="lamp" />
      <circle cx="97" cy="16" r="4" class="lamp" />
    </svg>
    <div class="empty-title">{{ title }}</div>
    <div v-if="description" class="empty-desc">{{ description }}</div>
    <slot />
  </div>
</template>

<script setup lang="ts">
defineProps<{ title: string; description?: string }>()
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--cg-space-2);
  padding: var(--cg-space-6) var(--cg-space-4);
  line-height: 1.5;
}
.empty-art {
  margin-bottom: var(--cg-space-2);
}
.ground,
.bar,
.bar-dash {
  fill: none;
  stroke-linecap: round;
}
.ground {
  stroke: var(--cg-border-strong);
  stroke-width: 2;
}
.post {
  fill: var(--cg-surface-2);
  stroke: var(--cg-border-strong);
  stroke-width: 1.5;
}
.bar {
  stroke: var(--cg-gold);
  stroke-width: 3;
}
.bar-dash {
  stroke: var(--cg-gold);
  stroke-width: 1.5;
  opacity: 0.6;
}
.lamp {
  fill: var(--cg-gold-soft);
  stroke: var(--cg-gold);
  stroke-width: 1.2;
}
.empty-title {
  font-size: var(--cg-text-lg);
  font-weight: 500;
  color: var(--cg-text-2);
  letter-spacing: 0.04em;
}
.empty-desc {
  font-size: var(--cg-text-sm);
  color: var(--cg-text-3);
}
</style>
