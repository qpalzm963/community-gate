type Listener = (data: Record<string, unknown>) => void

class WsHub {
  private ws: WebSocket | null = null
  private listeners = new Map<string, Set<Listener>>()
  private reconnectTimer: number | null = null
  private active = false

  connect() {
    this.active = true
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return
    }
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${location.host}/ws/events`)
    this.ws = ws

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as { type: string; data?: Record<string, unknown> }
        this.emit(msg.type, msg.data ?? {})
        this.emit('*', { type: msg.type, ...(msg.data ?? {}) })
      } catch {
        // ignore malformed message
      }
    }

    ws.onclose = () => {
      this.ws = null
      if (this.active) {
        this.reconnectTimer = window.setTimeout(() => this.connect(), 3000)
      }
    }
  }

  disconnect() {
    this.active = false
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.ws?.close()
    this.ws = null
  }

  on(type: string, fn: Listener): () => void {
    let set = this.listeners.get(type)
    if (!set) {
      set = new Set()
      this.listeners.set(type, set)
    }
    set.add(fn)
    return () => set?.delete(fn)
  }

  private emit(type: string, data: Record<string, unknown>) {
    this.listeners.get(type)?.forEach((fn) => fn(data))
  }
}

export const wsHub = new WsHub()

// 瀏覽器限制同時存在的 AudioContext 數量，每次響鈴都 new 一個且不關閉，響幾次後就再也沒有聲音；
// 因此整個頁面共用同一個。
let sharedAudioCtx: AudioContext | null = null

function getAudioContext(): AudioContext | null {
  if (sharedAudioCtx && sharedAudioCtx.state !== 'closed') return sharedAudioCtx
  const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!AudioCtx) return null
  sharedAudioCtx = new AudioCtx()
  return sharedAudioCtx
}

export function playAlertBeep(urgent = false) {
  try {
    const ctx = getAudioContext()
    if (!ctx) return
    // 尚未有使用者互動或分頁進入背景時會被瀏覽器暫停
    if (ctx.state === 'suspended') void ctx.resume()
    const freqs = urgent ? [880, 660, 880] : [740, 880]
    freqs.forEach((f, idx) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = urgent ? 'sawtooth' : 'sine'
      osc.frequency.value = f
      gain.gain.value = 0.08
      osc.connect(gain)
      gain.connect(ctx.destination)
      const start = ctx.currentTime + idx * 0.16
      osc.start(start)
      osc.stop(start + 0.13)
    })
  } catch {
    // ignore audio block
  }
}
