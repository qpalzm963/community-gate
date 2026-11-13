import { computed, ref } from 'vue'

export type ThemePreference = 'light' | 'dark' | 'auto'

const STORAGE_KEY = 'cg-theme'
const media = typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null

function readPreference(): ThemePreference {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'light' || v === 'dark' || v === 'auto') return v
  } catch {
    // 無痕模式等情況讀不到，使用預設
  }
  return 'auto'
}

const preference = ref<ThemePreference>(readPreference())
const systemDark = ref(media?.matches ?? false)
const isDark = computed(() => preference.value === 'dark' || (preference.value === 'auto' && systemDark.value))

function apply() {
  document.documentElement.classList.toggle('dark', isDark.value)
}

media?.addEventListener('change', (e) => {
  systemDark.value = e.matches
  apply()
})

/** 在 app mount 前呼叫，避免先閃一下淺色 */
export function initTheme() {
  apply()
}

export function useTheme() {
  function setPreference(p: ThemePreference) {
    preference.value = p
    try {
      localStorage.setItem(STORAGE_KEY, p)
    } catch {
      // 存不了就只在本次生效
    }
    apply()
  }

  /** 依序切換：跟隨系統 → 淺色 → 深色 */
  function cycle() {
    const order: ThemePreference[] = ['auto', 'light', 'dark']
    setPreference(order[(order.indexOf(preference.value) + 1) % order.length])
  }

  const label = computed(() => ({ auto: '跟隨系統', light: '淺色', dark: '深色' })[preference.value])

  return { preference, isDark, label, setPreference, cycle }
}
