<template>
  <!-- 徽章式 logo：盾形外框 + 社區名稱首字，色彩全取自 token -->
  <svg class="crest" :width="size" :height="size" viewBox="0 0 48 48" role="img" :aria-label="`${name} 標誌`">
    <path
      d="M24 3 L41 9 V23 C41 33.5 33.8 41.6 24 45 C14.2 41.6 7 33.5 7 23 V9 Z"
      class="crest-shield"
    />
    <path
      d="M24 6.6 L38 11.5 V23 C38 31.6 32.2 38.4 24 41.6 C15.8 38.4 10 31.6 10 23 V11.5 Z"
      class="crest-inner"
    />
    <text x="24" y="29.5" text-anchor="middle" class="crest-initial">{{ initial }}</text>
  </svg>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 40 })
const initial = computed(() => Array.from(props.name.trim())[0] ?? '社')
</script>

<style scoped>
.crest {
  flex-shrink: 0;
  display: block;
}
.crest-shield {
  fill: var(--cg-gold);
}
.crest-inner {
  fill: var(--cg-navy-deep);
  stroke: color-mix(in srgb, var(--cg-gold) 55%, transparent);
  stroke-width: 0.8;
}
.crest-initial {
  fill: var(--cg-gold);
  font-family: var(--cg-font-serif);
  font-size: 16px;
  font-weight: 600;
}
</style>
