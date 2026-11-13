import { computed, onUnmounted, ref, type Ref } from 'vue'

export interface CameraResolution {
  label: string
  width: number
  height: number
}

export const CAMERA_RESOLUTIONS: CameraResolution[] = [
  { label: '720p', width: 1280, height: 720 },
  { label: '480p', width: 854, height: 480 },
  { label: '1080p', width: 1920, height: 1080 },
]

type TorchCapabilities = MediaTrackCapabilities & { torch?: boolean }
type WakeLockSentinelLike = { release: () => Promise<void> }

/**
 * 手機相機擷取：開啟/切換鏡頭、解析度、補光燈，以及畫面常亮（Wake Lock）。
 * 只負責把影像接到 `videoEl`，推流交給 useLanePush。
 */
export function useCameraCapture(videoEl: Ref<HTMLVideoElement | null>, onStarted?: () => void) {
  const hasCamera = ref(true)
  const hasTorch = ref(false)
  const isTorchOn = ref(false)
  const errorMsg = ref('')
  const errorDesc = ref('')
  const facingMode = ref<'environment' | 'user'>('environment')
  const resIndex = ref(0)
  const currentResolution = computed(() => CAMERA_RESOLUTIONS[resIndex.value])

  let stream: MediaStream | null = null
  let wakeLock: WakeLockSentinelLike | null = null

  function stopStream() {
    stream?.getTracks().forEach((t) => t.stop())
    stream = null
  }

  async function requestWakeLock() {
    const nav = navigator as Navigator & { wakeLock?: { request: (type: 'screen') => Promise<WakeLockSentinelLike> } }
    if (!nav.wakeLock) return
    try {
      wakeLock = await nav.wakeLock.request('screen')
    } catch {
      // 省電模式等情況會被拒絕，不影響推流
    }
  }

  async function start() {
    errorMsg.value = ''
    errorDesc.value = ''

    if (!navigator.mediaDevices?.getUserMedia) {
      if (window.location.protocol !== 'https:' && window.location.hostname !== 'localhost') {
        errorMsg.value = '瀏覽器相機權限受限'
        errorDesc.value =
          '手機瀏覽器規定必須在 HTTPS 安全連線下才可授權開啟攝影機。請使用 https:// 網址連線（若提示不安全，請按「進階 → 繼續前往」）。'
      } else {
        errorMsg.value = '無法啟用攝影機'
        errorDesc.value = '此瀏覽器不支援相機存取功能。'
      }
      return
    }

    stopStream()
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
      const track = stream.getVideoTracks()[0]
      const caps = (track?.getCapabilities?.() ?? {}) as TorchCapabilities
      hasTorch.value = Boolean(caps.torch)
      isTorchOn.value = false
      onStarted?.()
    } catch (err) {
      hasCamera.value = false
      errorMsg.value = '無法取得相機權限'
      errorDesc.value = (err as Error)?.message || '請在手機瀏覽器設定中允許此網站存取相機。'
    }
  }

  function toggleFacing() {
    facingMode.value = facingMode.value === 'environment' ? 'user' : 'environment'
    void start()
  }

  function cycleResolution() {
    resIndex.value = (resIndex.value + 1) % CAMERA_RESOLUTIONS.length
    void start()
  }

  async function toggleTorch() {
    const track = stream?.getVideoTracks()[0]
    if (!track || !hasTorch.value) return
    isTorchOn.value = !isTorchOn.value
    try {
      await track.applyConstraints({ advanced: [{ torch: isTorchOn.value } as MediaTrackConstraintSet] })
    } catch {
      isTorchOn.value = false
    }
  }

  void requestWakeLock()

  onUnmounted(() => {
    stopStream()
    void wakeLock?.release()
    wakeLock = null
  })

  return {
    hasCamera,
    hasTorch,
    isTorchOn,
    errorMsg,
    errorDesc,
    facingMode,
    currentResolution,
    start,
    toggleFacing,
    cycleResolution,
    toggleTorch,
  }
}
