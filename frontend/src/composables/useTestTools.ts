import { ref, watch } from 'vue'

// 「模擬辨識 / 上傳圖片辨識」是測試用工具，正式值班畫面預設不顯示。
// 只存在這台瀏覽器（localStorage），不影響其他值班台。
const STORAGE_KEY = 'cg-test-tools'

function read(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

const enabled = ref(read())

watch(enabled, (v) => {
  try {
    localStorage.setItem(STORAGE_KEY, v ? '1' : '0')
  } catch {
    // 存不了就只在本次生效
  }
})

export function useTestTools() {
  return { testToolsEnabled: enabled }
}
