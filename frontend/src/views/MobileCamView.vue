<template>
  <div class="mobile-cam-container">
    <!-- 頂部資訊列 -->
    <header class="cam-header">
      <div class="lane-title">
        <span class="pulse-dot" :class="{ active: isConnected }"></span>
        <span class="title-text">{{ laneName || `車道 #${laneId}` }}</span>
      </div>
      <div class="status-tags">
        <span class="badge" :class="isConnected ? 'badge-success' : 'badge-danger'">
          {{ isConnected ? `已連線 ${fps}fps` : '連線中斷' }}
        </span>
      </div>
    </header>

    <!-- 視訊畫面區域 -->
    <main class="video-wrapper">
      <video ref="videoEl" autoplay playsinline muted class="video-preview"></video>
      <canvas ref="canvasEl" style="display: none;"></canvas>

      <!-- 錯誤/提示覆蓋層 -->
      <div v-if="errorMsg" class="error-overlay">
        <div class="error-card">
          <div class="error-icon">⚠️</div>
          <div class="error-title">{{ errorMsg }}</div>
          <p class="error-desc">{{ errorDesc }}</p>
          <button class="btn btn-primary" @click="initCamera">重新嘗試連線</button>
        </div>
      </div>

      <!-- 車牌辨識通知卡片 -->
      <transition name="slide-up">
        <div v-if="latestRecognition" class="recognition-card" :class="latestRecognition.decision === 'AUTO_ALLOW' ? 'allow' : 'warn'">
          <div class="rec-icon">🚗</div>
          <div class="rec-info">
            <div class="rec-plate">{{ latestRecognition.plate }}</div>
            <div class="rec-status">{{ categoryLabel(latestRecognition.category) }} · {{ decisionLabel(latestRecognition.decision) }}</div>
          </div>
        </div>
      </transition>
    </main>

    <!-- 底部控制工具列 -->
    <footer class="cam-footer">
      <button class="tool-btn" @click="toggleCamera" :disabled="!hasCamera">
        <span class="icon">🔄</span>
        <span class="label">{{ facingMode === 'environment' ? '後鏡頭' : '前鏡頭' }}</span>
      </button>

      <button class="tool-btn" @click="toggleResolution">
        <span class="icon">⚙️</span>
        <span class="label">{{ currentResolution.label }}</span>
      </button>

      <button class="tool-btn" :class="{ 'btn-active': isTorchOn }" @click="toggleTorch" v-if="hasTorch">
        <span class="icon">💡</span>
        <span class="label">補光燈</span>
      </button>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useCameraCapture } from '../composables/useCameraCapture'
import { useLanePush } from '../composables/useLanePush'

const CATEGORY_TEXT: Record<string, string> = {
  RESIDENT: '住戶車輛',
  VISITOR: '登記訪客',
  UNKNOWN: '未登記車輛',
  BLACKLIST: '黑名單車輛',
}

const DECISION_TEXT: Record<string, string> = {
  AUTO_ALLOW: '自動放行 (已開閘)',
  MANUAL_ALLOW: '管理員放行',
  DENY: '禁止進入',
  PENDING: '等待警衛審核',
}

const route = useRoute()
const laneId = computed(() => Number(route.query.lane || 1))
const token = computed(() => String(route.query.token || ''))
const laneName = ref('')

const videoEl = ref<HTMLVideoElement | null>(null)
const canvasEl = ref<HTMLCanvasElement | null>(null)

const { isConnected, fps, latestRecognition, start: startPush } = useLanePush(videoEl, canvasEl, laneId, token)
const {
  hasCamera,
  hasTorch,
  isTorchOn,
  errorMsg,
  errorDesc,
  facingMode,
  currentResolution,
  start: initCamera,
  toggleFacing: toggleCamera,
  cycleResolution: toggleResolution,
  toggleTorch,
} = useCameraCapture(videoEl, startPush)

function categoryLabel(cat: string) {
  return CATEGORY_TEXT[cat] || cat || '車輛'
}

function decisionLabel(dec: string) {
  return DECISION_TEXT[dec] || dec || ''
}

onMounted(() => {
  void initCamera()
})
</script>

<style scoped>
.mobile-cam-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100vw;
  background-color: #000;
  color: #fff;
  overflow: hidden;
  position: relative;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

.cam-header {
  height: 52px;
  background: rgba(15, 23, 42, 0.85);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  z-index: 10;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.5);
}

.lane-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pulse-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background-color: #ef4444;
}

.pulse-dot.active {
  background-color: #10b981;
  box-shadow: 0 0 8px #10b981;
}

.title-text {
  font-weight: 600;
  font-size: 16px;
  color: #f8fafc;
}

.badge {
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 12px;
  font-weight: 500;
}

.badge-success {
  background-color: rgba(16, 185, 129, 0.2);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.4);
}

.badge-danger {
  background-color: rgba(239, 68, 68, 0.2);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.4);
}

.video-wrapper {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: #000;
  overflow: hidden;
}

.video-preview {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.error-overlay {
  position: absolute;
  inset: 0;
  background: rgba(15, 23, 42, 0.92);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  z-index: 20;
}

.error-card {
  background: #1e293b;
  border-radius: 16px;
  padding: 24px;
  text-align: center;
  max-width: 340px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.6);
}

.error-icon {
  font-size: 44px;
  margin-bottom: 12px;
}

.error-title {
  font-size: 18px;
  font-weight: bold;
  color: #f8fafc;
  margin-bottom: 8px;
}

.error-desc {
  font-size: 13px;
  line-height: 1.5;
  color: #94a3b8;
  margin-bottom: 20px;
}

.btn {
  display: inline-block;
  padding: 10px 20px;
  border-radius: 8px;
  font-weight: 600;
  border: none;
  cursor: pointer;
}

.btn-primary {
  background-color: #3b82f6;
  color: #fff;
}

.recognition-card {
  position: absolute;
  bottom: 20px;
  left: 16px;
  right: 16px;
  background: rgba(15, 23, 42, 0.95);
  border-radius: 12px;
  padding: 14px 18px;
  display: flex;
  align-items: center;
  gap: 14px;
  backdrop-filter: blur(10px);
  z-index: 15;
  border-left: 6px solid #10b981;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.7);
}

.recognition-card.warn {
  border-left-color: #f59e0b;
}

.rec-icon {
  font-size: 32px;
}

.rec-info {
  flex: 1;
}

.rec-plate {
  font-size: 22px;
  font-weight: 800;
  letter-spacing: 1px;
  color: #ffffff;
}

.rec-status {
  font-size: 13px;
  color: #94a3b8;
  margin-top: 2px;
}

.cam-footer {
  height: 68px;
  background: rgba(15, 23, 42, 0.85);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 0 12px;
  z-index: 10;
}

.tool-btn {
  background: transparent;
  border: none;
  color: #cbd5e1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 8px;
}

.tool-btn .icon {
  font-size: 20px;
}

.tool-btn.btn-active {
  color: #fbbf24;
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(40px);
  opacity: 0;
}
</style>
