import { reactive } from 'vue'
import { api, type AccessEvent, type AlertItem, type User } from './api'
import { playAlertBeep, wsHub } from './ws'

export const appState = reactive({
  user: null as User | null,
  communityName: '社區出入管理系統',
  alertSound: true,
  unackAlerts: 0,
  pendingEvents: [] as AccessEvent[],
  gateAnim: {} as Record<number, { text: string; ok: boolean; until: number }>,
})

let initialized = false

export async function loadPublicInfo() {
  try {
    const info = await api.get<{ community_name: string }>('/api/public/info')
    appState.communityName = info.community_name || '社區出入管理系統'
    document.title = appState.communityName
  } catch {
    // ignore
  }
}

export async function refreshPendingAndAlerts() {
  if (!appState.user) return
  try {
    const [pending, dash, settings] = await Promise.all([
      api.get<AccessEvent[]>('/api/events/pending'),
      api.get<{ unack_alerts: number }>('/api/dashboard'),
      api.get<{ values: Record<string, unknown> }>('/api/settings'),
    ])
    appState.pendingEvents = pending
    appState.unackAlerts = dash.unack_alerts
    appState.alertSound = Boolean(settings.values.alert_sound ?? true)
  } catch {
    // ignore
  }
}

export function initWsListeners() {
  if (initialized) return
  initialized = true

  // 每次（重新）連上 WebSocket 後端都會先送 hello；斷線期間錯過的推播（例如未登記車輛）要靠這裡補抓
  wsHub.on('hello', () => {
    void refreshPendingAndAlerts()
  })

  wsHub.on('access_event', (raw) => {
    const ev = raw as unknown as AccessEvent
    if (ev.decision === 'PENDING') {
      if (!appState.pendingEvents.some((p) => p.id === ev.id)) {
        appState.pendingEvents.unshift(ev)
      }
      if (appState.alertSound) playAlertBeep(false)
    }
  })

  wsHub.on('access_event_updated', (raw) => {
    const ev = raw as unknown as AccessEvent
    appState.pendingEvents = appState.pendingEvents.filter((p) => p.id !== ev.id)
    void refreshPendingAndAlerts()
  })

  wsHub.on('alert', (raw) => {
    const a = raw as unknown as AlertItem
    appState.unackAlerts += 1
    if (appState.alertSound && a.type === 'BLACKLIST') {
      playAlertBeep(true)
    }
  })

  wsHub.on('alerts_changed', () => {
    void refreshPendingAndAlerts()
  })

  wsHub.on('settings_changed', (vals) => {
    if (typeof vals.community_name === 'string') {
      appState.communityName = vals.community_name
      document.title = vals.community_name
    }
    if (typeof vals.alert_sound === 'boolean') {
      appState.alertSound = vals.alert_sound
    }
  })

  wsHub.on('gate', (data) => {
    const laneId = Number(data.lane_id)
    const ok = Boolean(data.ok)
    const message = String(data.message ?? '')
    appState.gateAnim[laneId] = {
      text: ok ? `柵欄已開啟（${message}）` : `開閘失敗：${message}`,
      ok,
      until: Date.now() + 4500,
    }
  })
}
