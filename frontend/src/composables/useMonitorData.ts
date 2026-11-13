import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { api, type AccessEvent, type DashboardStats, type Lane, type PresenceItem } from '../api'
import { wsHub } from '../ws'

/** 即時監控頁的資料：車道、今日統計、最新紀錄、在場車輛，並跟著 WebSocket 推播自動更新。 */
export function useMonitorData() {
  const lanes = ref<Lane[]>([])
  const recentEvents = ref<AccessEvent[]>([])
  const presence = ref<PresenceItem[]>([])
  const stats = reactive<DashboardStats>({
    today_in: 0,
    today_out: 0,
    today_denied: 0,
    pending: 0,
    onsite_vehicles: 0,
    onsite_visitors: 0,
    overstay_visitors: 0,
    unack_alerts: 0,
  })
  const enabledLanes = computed(() => lanes.value.filter((l) => l.enabled))

  async function loadAll() {
    const [l, d, ev, p] = await Promise.all([
      api.get<Lane[]>('/api/lanes'),
      api.get<DashboardStats>('/api/dashboard'),
      api.get<{ items: AccessEvent[] }>('/api/events?page=1&page_size=20'),
      api.get<PresenceItem[]>('/api/presence'),
    ])
    lanes.value = l
    Object.assign(stats, d)
    recentEvents.value = ev.items
    presence.value = p
  }

  const unsubs: Array<() => void> = []

  onMounted(() => {
    void loadAll()
    unsubs.push(
      wsHub.on('access_event', () => void loadAll()),
      wsHub.on('access_event_updated', () => void loadAll()),
      // 斷線重連後補抓斷線期間的變化
      wsHub.on('hello', () => void loadAll()),
      wsHub.on('lane_status', (st) => {
        const target = lanes.value.find((l) => l.id === Number(st.lane_id))
        if (target) target.status = st as unknown as Lane['status']
      }),
    )
  })

  onUnmounted(() => {
    unsubs.forEach((u) => u())
  })

  return { lanes, enabledLanes, recentEvents, presence, stats, loadAll }
}
