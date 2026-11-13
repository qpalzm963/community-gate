<template>
  <article class="lane-card" :class="{ online: lane.status?.online }">
    <header class="lane-head">
      <div class="lane-title">
        <h3>{{ lane.name }}</h3>
        <span class="lane-meta">{{ DIRECTION_LABEL[lane.direction] }} · {{ VEHICLE_TYPE_LABEL[lane.vehicle_types] }}</span>
      </div>
      <div class="lane-actions">
        <el-button size="small" :icon="Iphone" @click="emit('show-qr', lane)">手機鏡頭</el-button>
        <el-button type="primary" size="small" :icon="Unlock" @click="manualOpenGate">手動開閘</el-button>
      </div>
    </header>

    <div class="stream-wrap">
      <img :src="`/api/lanes/${lane.id}/stream`" class="stream-img" :alt="`${lane.name} 即時畫面`" />
      <div class="stream-vignette" aria-hidden="true" />
      <div class="stream-info top">
        <span class="live-chip" :class="lane.status?.online ? 'on' : 'off'">
          <span class="live-dot" />
          {{ lane.status?.online ? `LIVE · ${lane.status.capture_fps ?? '—'} fps` : '離線 / 未接攝影機' }}
        </span>
      </div>
      <div class="stream-info bottom">
        <span class="stream-lane">{{ lane.name }}</span>
      </div>
      <transition name="fade-rise">
        <div v-if="banner" class="gate-banner" :class="banner.ok ? 'ok' : 'err'" role="status">
          <el-icon><component :is="banner.ok ? CircleCheck : CircleClose" /></el-icon>
          {{ banner.text }}
        </div>
      </transition>
    </div>

    <div class="lane-tools">
      <el-input
        v-model="simPlate"
        size="small"
        placeholder="輸入車牌模擬辨識（例 ABC-1234）"
        class="sim-input"
        @keyup.enter="simulatePlate"
      />
      <el-button size="small" @click="simulatePlate">模擬辨識</el-button>
      <el-upload
        :show-file-list="false"
        accept="image/*"
        :http-request="(opt: UploadRequestOptions) => uploadRecognize(opt.file)"
      >
        <el-button size="small" text :icon="Picture">上傳圖片辨識</el-button>
      </el-upload>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, type UploadRequestOptions } from 'element-plus'
import { CircleCheck, CircleClose, Iphone, Picture, Unlock } from '@element-plus/icons-vue'
import { api, DECISION_LABEL, DIRECTION_LABEL, VEHICLE_TYPE_LABEL, type AccessEvent, type Lane } from '../api'
import { appState } from '../store'

const props = defineProps<{ lane: Lane; nowTick: number }>()
const emit = defineEmits<{
  (e: 'show-qr', lane: Lane): void
  /** 車道上有動作（開閘、模擬、上傳辨識）後，請父層重新載入資料 */
  (e: 'changed'): void
}>()

const simPlate = ref('')

const banner = computed(() => {
  const g = appState.gateAnim[props.lane.id]
  if (!g || g.until < props.nowTick) return null
  return g
})

async function manualOpenGate() {
  try {
    await api.post(`/api/lanes/${props.lane.id}/open`, { note: '即時監控手動開閘' })
    ElMessage.success(`${props.lane.name} 已開閘`)
    emit('changed')
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function simulatePlate() {
  const plate = simPlate.value.trim()
  if (!plate) return
  try {
    await api.post(`/api/lanes/${props.lane.id}/simulate`, { plate })
    simPlate.value = ''
    emit('changed')
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

interface RecognizeResult {
  detections: Array<{ plate_display: string | null; raw_text: string; confidence: number }>
  event: AccessEvent | null
}

async function uploadRecognize(file: File) {
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await api.upload<RecognizeResult>(`/api/lanes/${props.lane.id}/recognize?apply=true`, form)
    if (res.event) {
      ElMessage.success(`辨識結果：${res.event.plate_display}（${DECISION_LABEL[res.event.decision]}）`)
    } else if (res.detections.length > 0) {
      ElMessage.warning(`僅偵測到：${res.detections.map((d) => d.raw_text).join(', ')}（未符合車牌格式）`)
    } else {
      ElMessage.info('圖片中未偵測到車牌')
    }
    emit('changed')
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}
</script>

<style scoped>
.lane-card {
  position: relative;
  padding: 18px;
  border-radius: var(--cg-radius-lg);
  border: 1px solid var(--cg-border);
  background: var(--cg-surface);
  box-shadow: var(--cg-shadow-sm);
  overflow: hidden;
}
/* 左側細色條：車道連線狀態 */
.lane-card::before {
  content: "";
  position: absolute;
  left: 0;
  top: 18px;
  bottom: 18px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--cg-border-strong);
}
.lane-card.online::before {
  background: var(--cg-success);
}
.lane-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--cg-space-2);
  margin-bottom: 14px;
}
.lane-title h3 {
  margin: 0;
  font-family: var(--cg-font-serif);
  font-size: var(--cg-text-lg);
  font-weight: 600;
  letter-spacing: 0.06em;
}
.lane-meta {
  font-size: var(--cg-text-xs);
  letter-spacing: 0.1em;
  color: var(--cg-text-3);
}
.lane-actions {
  display: flex;
  gap: var(--cg-space-2);
}

.stream-wrap {
  position: relative;
  background: var(--cg-media-bg);
  border-radius: var(--cg-radius-md);
  overflow: hidden;
  aspect-ratio: 16 / 9;
}
.stream-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.stream-vignette {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(120% 90% at 50% 45%, transparent 55%, var(--cg-overlay) 100%),
    linear-gradient(180deg, var(--cg-overlay) 0%, transparent 22%, transparent 70%, var(--cg-overlay) 100%);
}
.stream-info {
  position: absolute;
  left: 12px;
  right: 12px;
  display: flex;
  justify-content: space-between;
  pointer-events: none;
}
.stream-info.top {
  top: 10px;
  justify-content: flex-end;
}
.stream-info.bottom {
  bottom: 10px;
}
.stream-lane {
  font-size: var(--cg-text-sm);
  letter-spacing: 0.1em;
  color: var(--cg-overlay-text);
}
.live-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: var(--cg-radius-pill);
  font-family: var(--cg-font-mono);
  font-size: var(--cg-text-xs);
  letter-spacing: 0.06em;
  color: var(--cg-overlay-text);
  background: var(--cg-overlay);
  backdrop-filter: blur(6px);
}
.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cg-side-text-dim);
}
.live-chip.on .live-dot {
  background: var(--cg-success-text);
  animation: pulse 1.8s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.35; }
}

.gate-banner {
  position: absolute;
  bottom: 40px;
  left: 0;
  right: 0;
  width: fit-content;
  margin: 0 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 18px;
  border-radius: var(--cg-radius-pill);
  font-weight: 500;
  font-size: var(--cg-text-md);
  color: var(--cg-text-inverse);
  background: var(--cg-overlay);
  border: 1px solid currentColor;
  backdrop-filter: blur(8px);
  box-shadow: var(--cg-shadow-md);
  white-space: nowrap;
}
.gate-banner.ok {
  border-color: var(--cg-success);
  background: color-mix(in srgb, var(--cg-success) 82%, var(--cg-media-bg));
}
.gate-banner.err {
  border-color: var(--cg-danger);
  background: color-mix(in srgb, var(--cg-danger) 82%, var(--cg-media-bg));
}

.lane-tools {
  display: flex;
  gap: var(--cg-space-2);
  align-items: center;
  margin-top: 14px;
  flex-wrap: wrap;
}
.sim-input {
  width: 230px;
}
</style>
