import { onUnmounted, ref, type Ref } from 'vue'

export interface RecognitionInfo {
  plate: string
  category: string
  decision: string
}

export interface LanePushOptions {
  /** 擷取間隔（毫秒），預設 100ms ≈ 10fps */
  intervalMs?: number
  /** 送出影格的最大寬度，超過會等比縮小 */
  maxWidth?: number
  jpegQuality?: number
  /** 辨識通知卡片顯示多久（毫秒） */
  recognitionTtlMs?: number
}

/**
 * 把 `<video>` 的畫面定時轉成 JPEG，透過 WebSocket 推給後端車道辨識，
 * 並接收後端回傳的車牌確認通知。斷線 3 秒後自動重連，元件卸載後停止。
 */
export function useLanePush(
  videoEl: Ref<HTMLVideoElement | null>,
  canvasEl: Ref<HTMLCanvasElement | null>,
  laneId: Ref<number>,
  token: Ref<string>,
  options: LanePushOptions = {},
) {
  const { intervalMs = 100, maxWidth = 960, jpegQuality = 0.72, recognitionTtlMs = 5000 } = options

  const isConnected = ref(false)
  const fps = ref(0)
  const latestRecognition = ref<RecognitionInfo | null>(null)

  let ws: WebSocket | null = null
  let active = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let captureTimer: ReturnType<typeof setInterval> | null = null
  let fpsTimer: ReturnType<typeof setInterval> | null = null
  let recClearTimer: ReturnType<typeof setTimeout> | null = null
  let frameCount = 0

  function handleMessage(e: MessageEvent) {
    let msg: { type?: string } & Partial<RecognitionInfo>
    try {
      msg = JSON.parse(e.data)
    } catch {
      return
    }
    if (msg.type !== 'plate_confirmed') return
    latestRecognition.value = { plate: msg.plate ?? '', category: msg.category ?? '', decision: msg.decision ?? '' }
    try {
      navigator.vibrate?.([100, 50, 100])
    } catch {
      // 部分瀏覽器不支援震動
    }
    if (recClearTimer) clearTimeout(recClearTimer)
    recClearTimer = setTimeout(() => {
      latestRecognition.value = null
    }, recognitionTtlMs)
  }

  function connect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.onclose = null
      ws.close()
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/ws/lanes/${laneId.value}/push?token=${encodeURIComponent(token.value)}`
    const sock = new WebSocket(url)
    sock.binaryType = 'blob'
    sock.onopen = () => {
      isConnected.value = true
    }
    sock.onerror = () => {
      isConnected.value = false
    }
    sock.onmessage = handleMessage
    sock.onclose = () => {
      isConnected.value = false
      if (ws === sock) ws = null
      if (active) reconnectTimer = setTimeout(connect, 3000)
    }
    ws = sock
  }

  function captureFrame() {
    const sock = ws
    if (!isConnected.value || !sock || sock.readyState !== WebSocket.OPEN) return
    const v = videoEl.value
    const c = canvasEl.value
    if (!v || !c || v.videoWidth === 0) return

    const w = Math.min(v.videoWidth, maxWidth)
    const h = Math.round((v.videoHeight * w) / v.videoWidth)
    if (c.width !== w || c.height !== h) {
      c.width = w
      c.height = h
    }
    const ctx = c.getContext('2d')
    if (!ctx) return
    ctx.drawImage(v, 0, 0, w, h)
    c.toBlob(
      (blob) => {
        if (blob && ws && ws.readyState === WebSocket.OPEN) {
          ws.send(blob)
          frameCount++
        }
      },
      'image/jpeg',
      jpegQuality,
    )
  }

  function clearTimers() {
    if (captureTimer) clearInterval(captureTimer)
    if (fpsTimer) clearInterval(fpsTimer)
    captureTimer = fpsTimer = null
  }

  /** 開始（或重新開始）推流；切換鏡頭/解析度後再呼叫一次即可。 */
  function start() {
    active = true
    connect()
    clearTimers()
    captureTimer = setInterval(captureFrame, intervalMs)
    fpsTimer = setInterval(() => {
      fps.value = frameCount
      frameCount = 0
    }, 1000)
  }

  function stop() {
    active = false
    clearTimers()
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (recClearTimer) clearTimeout(recClearTimer)
    reconnectTimer = recClearTimer = null
    if (ws) {
      ws.onclose = null
      ws.close()
      ws = null
    }
    isConnected.value = false
  }

  onUnmounted(stop)

  return { isConnected, fps, latestRecognition, start, stop }
}
