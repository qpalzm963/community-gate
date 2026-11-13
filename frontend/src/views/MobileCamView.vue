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
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const laneId = computed(() => Number(route.query.lane || 1))
const token = computed(() => String(route.query.token || ''))

const laneName = ref('')
const videoEl = ref<HTMLVideoElement | null>(null)
const canvasEl = ref<HTMLCanvasElement | null>(null)

const isConnected = ref(false)
const hasCamera = ref(true)
const hasTorch = ref(false)
const isTorchOn = ref(false)
const errorMsg = ref('')
const errorDesc = ref('')
const fps = ref(0)
const facingMode = ref<'environment' | 'user'>('environment')

const resolutions = [
  { label: '720p', width: 1280, height: 720 },
  { label: '480p', width: 854, height: 480 },
  { label: '1080p', width: 1920, height: 1080 },
]
const resIndex = ref(0)
const currentResolution = computed(() => resolutions[resIndex.value])

interface RecognitionInfo {
  plate: string
  category: string
  decision: string
}
const latestRecognition = ref<RecognitionInfo | null>(null)
let recClearTimer: ReturnType<typeof setTimeout> | null = null

let stream: MediaStream | null = null
let ws: WebSocket | null = null
let captureTimer: ReturnType<typeof setInterval> | null = null
let fpsTimer: ReturnType<typeof setInterval> | null = null
let frameCount = 0
let wakeLockSentinel: any = null

function categoryLabel(cat: string) {
  const map: Record<string, string> = {
    RESIDENT: '住戶車輛',
    VISITOR: '登記訪客',
    UNKNOWN: '未登記車輛',
    BLACKLIST: '黑名單車輛',
  }
  return map[cat] || cat || '車輛'
}

function decisionLabel(dec: string) {
  const map: Record<string, string> = {
    AUTO_ALLOW: '自動放行 (已開閘)',
    MANUAL_ALLOW: '管理員放行',
    DENY: '禁止進入',
    PENDING: '等待警衛審核',
  }
  return map[dec] || dec || ''
}

async function initWakeLock() {
  if ('wakeLock' in navigator) {
    try {
      wakeLockSentinel = await (navigator as any).wakeLock.request('screen')
    } catch {
      // ignore
    }
  }
}

async function initCamera() {
  errorMsg.value = ''
  errorDesc.value = ''

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') {
      errorMsg.value = '瀏覽器相機權限受限'
      errorDesc.value = '手機瀏覽器規定必須在 HTTPS 安全連線下才可授權開啟攝影機。請使用 https:// 網址連線（若提示不安全，請按「進階 → 繼續前往」）。'
    } else {
      errorMsg.value = '無法啟用攝影機'
      errorDesc.value = '此瀏覽器不支援相機存取功能。'
    }
    return
  }

  if (stream) {
    stream.getTracks().forEach((t) => t.stop())
    stream = null
  }

  try {
    const res = currentResolution.value
    stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: { ideal: facingMode.value },
        width: { ideal: res.width },
        height: { ideal: res.height },
      },
      audio: false,
    })

    if (videoEl.value) {
      videoEl.value.srcObject = stream
      await videoEl.value.play()
    }

    // 檢查是否有手電筒/補光燈功能
    const track = stream.getVideoTracks()[0]
    if (track) {
      const caps = track.getCapabilities ? (track.getCapabilities() as any) : {}
      hasTorch.value = Boolean(caps.torch)
    }

    startPushStream()
  } catch (err: any) {
    hasCamera.value = false
    errorMsg.value = '無法取得相機權限'
    errorDesc.value = err?.message || '請在手機瀏覽器設定中允許此網站存取相機。'
  }
}

function toggleCamera() {
  facingMode.value = facingMode.value === 'environment' ? 'user' : 'environment'
  void initCamera()
}

function toggleResolution() {
  resIndex.value = (resIndex.value + 1) % resolutions.length
  void initCamera()
}

async function toggleTorch() {
  if (!stream || !hasTorch.value) return
  const track = stream.getVideoTracks()[0]
  if (!track) return
  isTorchOn.value = !isTorchOn.value
  try {
    await (track as any).applyConstraints({
      advanced: [{ torch: isTorchOn.value }],
    })
  } catch {
    isTorchOn.value = false
  }
}

function connectWs() {
  if (ws) {
    ws.close()
    ws = null
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/ws/lanes/${laneId.value}/push?token=${encodeURIComponent(token.value)}`

  ws = new WebSocket(wsUrl)
  ws.binaryType = 'blob'

  ws.onopen = () => {
    isConnected.value = true
  }

  ws.onclose = () => {
    isConnected.value = false
    // 3 秒後自動重試連線
    setTimeout(() => {
      if (!ws || ws.readyState === WebSocket.CLOSED) {
        connectWs()
      }
    }, 3000)
  }

  ws.onerror = () => {
    isConnected.value = false
  }

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'plate_confirmed') {
        latestRecognition.value = {
          plate: msg.plate,
          category: msg.category,
          decision: msg.decision,
        }
        // 手機震動反饋
        if ('vibrate' in navigator) {
          try {
            navigator.vibrate([100, 50, 100])
          } catch {}
        }
        if (recClearTimer) clearTimeout(recClearTimer)
        recClearTimer = setTimeout(() => {
          latestRecognition.value = null
        }, 5000)
      }
    } catch {}
  }
}

function startPushStream() {
  connectWs()

  if (captureTimer) clearInterval(captureTimer)
  if (fpsTimer) clearInterval(fpsTimer)

  // 每秒送約 10 張影格 (100ms)
  captureTimer = setInterval(() => {
    if (!isConnected.value || !ws || ws.readyState !== WebSocket.OPEN) return
    const v = videoEl.value
    const c = canvasEl.value
    if (!v || !c || v.videoWidth === 0) return

    // 依縮放比例繪製影格
    const targetW = Math.min(v.videoWidth, 960)
    const targetH = Math.round((v.videoHeight * targetW) / v.videoWidth)

    if (c.width !== targetW || c.height !== targetH) {
      c.width = targetW
      c.height = targetH
    }

    const ctx = c.getContext('2d')
    if (!ctx) return
    ctx.drawImage(v, 0, 0, targetW, targetH)

    c.toBlob(
      (blob) => {
        if (blob && ws && ws.readyState === WebSocket.OPEN) {
          ws.send(blob)
          frameCount++
        }
      },
      'image/jpeg',
      0.72,
    )
  }, 100)

  // 計算實際送出之 FPS
  fpsTimer = setInterval(() => {
    fps.value = frameCount
    frameCount = 0
  }, 1000)
}

onMounted(() => {
  void initWakeLock()
  void initCamera()
})

onUnmounted(() => {
  if (captureTimer) clearInterval(captureTimer)
  if (fpsTimer) clearInterval(fpsTimer)
  if (recClearTimer) clearTimeout(recClearTimer)
  if (stream) {
    stream.getTracks().forEach((t) => t.stop())
    stream = null
  }
  if (ws) {
    ws.close()
    ws = null
  }
  if (wakeLockSentinel) {
    wakeLockSentinel.release()
    wakeLockSentinel = null
  }
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
