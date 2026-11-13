<template>
  <div>
    <div class="page-header">
      <h2 class="page-title">即時監控</h2>
      <div style="display: flex; gap: 8px">
        <el-button @click="loadAll" :icon="Refresh">重新整理</el-button>
      </div>
    </div>

    <!-- 今日統計 -->
    <el-row :gutter="12" style="margin-bottom: 16px">
      <el-col :xs="12" :sm="8" :md="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">今日進場</div>
          <div class="stat-val text-primary">{{ stats.today_in }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">今日離場</div>
          <div class="stat-val">{{ stats.today_out }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">目前在場車輛</div>
          <div class="stat-val text-success">{{ stats.onsite_vehicles }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">在場／逾時訪客</div>
          <div class="stat-val">
            {{ stats.onsite_visitors }}
            <span v-if="stats.overstay_visitors" class="text-danger">({{ stats.overstay_visitors }})</span>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="4">
        <el-card shadow="never" class="stat-card">
          <div class="stat-label">今日拒絕</div>
          <div class="stat-val text-danger">{{ stats.today_denied }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="8" :md="4">
        <el-card shadow="never" class="stat-card" style="cursor: pointer" @click="router.push('/alerts')">
          <div class="stat-label">未處理警示</div>
          <div class="stat-val" :class="stats.unack_alerts ? 'text-danger' : ''">{{ stats.unack_alerts }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 車道即時畫面 -->
    <el-row :gutter="16" style="margin-bottom: 16px">
      <el-col v-for="lane in enabledLanes" :key="lane.id" :xs="24" :md="12" style="margin-bottom: 12px">
        <el-card shadow="never">
          <template #header>
            <div class="lane-head">
              <div>
                <strong>{{ lane.name }}</strong>
                <el-tag size="small" style="margin-left: 8px">{{ DIRECTION_LABEL[lane.direction] }}</el-tag>
                <el-tag size="small" type="info" style="margin-left: 4px">
                  {{ VEHICLE_TYPE_LABEL[lane.vehicle_types] }}
                </el-tag>
              </div>
              <div style="display: flex; align-items: center; gap: 8px">
                <el-tag :type="lane.status?.online ? 'success' : 'info'" size="small">
                  {{ lane.status?.online ? `連線中 ${lane.status.capture_fps ?? ''}fps` : '離線 / 未接攝影機' }}
                </el-tag>
                <el-button size="small" @click="showQr(lane)">📱 手機鏡頭</el-button>
                <el-button type="primary" size="small" @click="manualOpenGate(lane)">手動開閘</el-button>
              </div>
            </div>
          </template>

          <div class="stream-wrap">
            <img :src="`/api/lanes/${lane.id}/stream`" class="stream-img" :alt="lane.name" />
            <div
              v-if="gateBanner(lane.id)"
              class="gate-banner"
              :class="gateBanner(lane.id)?.ok ? 'ok' : 'err'"
            >
              {{ gateBanner(lane.id)?.text }}
            </div>
          </div>

          <div class="lane-tools">
            <el-input
              v-model="simPlate[lane.id]"
              size="small"
              placeholder="輸入車牌模擬辨識 (例 ABC-1234)"
              style="width: 210px"
              @keyup.enter="simulatePlate(lane.id)"
            />
            <el-button size="small" @click="simulatePlate(lane.id)">模擬辨識</el-button>
            <el-upload
              :show-file-list="false"
              accept="image/*"
              :http-request="(opt: UploadRequestOptions) => uploadRecognize(lane.id, opt.file)"
            >
              <el-button size="small" plain>上傳圖片辨識</el-button>
            </el-upload>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 即時紀錄 / 目前在場車輛 -->
    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="最新進出紀錄" name="events">
          <el-table :data="recentEvents" size="small" stripe>
            <el-table-column label="時間" width="165">
              <template #default="{ row }">{{ fmtDateTime(row.occurred_at) }}</template>
            </el-table-column>
            <el-table-column prop="lane_name" label="車道" width="110" />
            <el-table-column label="方向" width="75">
              <template #default="{ row }">{{ DIRECTION_LABEL[row.direction] }}</template>
            </el-table-column>
            <el-table-column label="車牌" width="130">
              <template #default="{ row }">
                <span v-if="row.plate_display" class="plate-badge">{{ row.plate_display }}</span>
                <span v-else style="color: #94a3b8">—</span>
              </template>
            </el-table-column>
            <el-table-column label="車種" width="75">
              <template #default="{ row }">{{ VEHICLE_TYPE_LABEL[row.vehicle_type] }}</template>
            </el-table-column>
            <el-table-column label="類別" width="90">
              <template #default="{ row }">
                <el-tag :type="categoryTag(row.category)" size="small">{{ CATEGORY_LABEL[row.category] }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="結果" width="100">
              <template #default="{ row }">
                <el-tag :type="decisionTag(row.decision)" size="small">{{ DECISION_LABEL[row.decision] }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="household_unit" label="戶別" width="100" />
            <el-table-column prop="note" label="備註" min-width="140" show-overflow-tooltip />
            <el-table-column label="截圖" width="80">
              <template #default="{ row }">
                <el-button v-if="row.snapshot_url" link type="primary" size="small" @click="previewEvent = row">
                  檢視
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane :label="`目前在場車輛 (${presence.length})`" name="presence">
          <el-table :data="presence" size="small" stripe>
            <el-table-column label="車牌" width="140">
              <template #default="{ row }">
                <span class="plate-badge">{{ row.plate_display }}</span>
              </template>
            </el-table-column>
            <el-table-column label="車種" width="80">
              <template #default="{ row }">{{ VEHICLE_TYPE_LABEL[row.vehicle_type] || '未知' }}</template>
            </el-table-column>
            <el-table-column label="類別" width="95">
              <template #default="{ row }">{{ CATEGORY_LABEL[row.category] || row.category || '—' }}</template>
            </el-table-column>
            <el-table-column prop="household_unit" label="戶別" width="120" />
            <el-table-column label="進場時間" width="180">
              <template #default="{ row }">{{ fmtDateTime(row.entered_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="120">
              <template #default="{ row }">
                <el-button link type="warning" size="small" @click="closePresence(row.id)">手動結清離場</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="previewVisible" title="事件截圖" width="700px">
      <div v-if="previewEvent" style="text-align: center">
        <div style="margin-bottom: 10px">
          <span class="plate-badge lg">{{ previewEvent.plate_display || '無車牌' }}</span>
          <span style="margin-left: 12px; color: #64748b">{{ fmtDateTime(previewEvent.occurred_at) }}</span>
        </div>
        <img v-if="previewEvent.plate_crop_url" :src="previewEvent.plate_crop_url" style="max-height: 70px; margin-bottom: 10px" />
        <img v-if="previewEvent.snapshot_url" :src="previewEvent.snapshot_url" style="width: 100%; border-radius: 6px" />
      </div>
    </el-dialog>

    <MobileCameraQrDialog v-model="qrDlg" :lane="qrLane" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type UploadRequestOptions } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import MobileCameraQrDialog from '../components/MobileCameraQrDialog.vue'
import {
  api,
  CATEGORY_LABEL,
  DECISION_LABEL,
  DIRECTION_LABEL,
  fmtDateTime,
  VEHICLE_TYPE_LABEL,
  type AccessEvent,
  type DashboardStats,
  type Lane,
  type PresenceItem,
} from '../api'
import { appState } from '../store'
import { wsHub } from '../ws'

const router = useRouter()
const lanes = ref<Lane[]>([])
const recentEvents = ref<AccessEvent[]>([])
const presence = ref<PresenceItem[]>([])
const activeTab = ref('events')
const simPlate = reactive<Record<number, string>>({})
const previewEvent = ref<AccessEvent | null>(null)
const nowTick = ref(Date.now())
let timer: number | null = null

const qrDlg = ref(false)
const qrLane = ref<Lane | null>(null)

function showQr(lane: Lane) {
  qrLane.value = lane
  qrDlg.value = true
}

const previewVisible = computed({
  get: () => !!previewEvent.value,
  set: (v) => {
    if (!v) previewEvent.value = null
  },
})

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

function gateBanner(laneId: number) {
  const g = appState.gateAnim[laneId]
  if (!g || g.until < nowTick.value) return null
  return g
}

function categoryTag(c: string) {
  if (c === 'RESIDENT') return 'success'
  if (c === 'VISITOR') return 'primary'
  if (c === 'BLACKLIST') return 'danger'
  if (c === 'UNKNOWN') return 'warning'
  return 'info'
}

function decisionTag(d: string) {
  if (d === 'AUTO_ALLOW' || d === 'MANUAL_ALLOW') return 'success'
  if (d === 'DENY') return 'danger'
  return 'warning'
}

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

async function manualOpenGate(lane: Lane) {
  try {
    await api.post(`/api/lanes/${lane.id}/open`, { note: '即時監控手動開閘' })
    ElMessage.success(`${lane.name} 已開閘`)
    void loadAll()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function simulatePlate(laneId: number) {
  const plate = (simPlate[laneId] || '').trim()
  if (!plate) return
  try {
    await api.post(`/api/lanes/${laneId}/simulate`, { plate })
    simPlate[laneId] = ''
    void loadAll()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function uploadRecognize(laneId: number, file: File) {
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await api.upload<{ detections: Array<{ plate_display: string | null; raw_text: string; confidence: number }>; event: AccessEvent | null }>(
      `/api/lanes/${laneId}/recognize?apply=true`,
      form,
    )
    if (res.event) {
      ElMessage.success(`辨識結果：${res.event.plate_display}（${DECISION_LABEL[res.event.decision]}）`)
    } else if (res.detections.length > 0) {
      ElMessage.warning(`僅偵測到：${res.detections.map((d) => d.raw_text).join(', ')}（未符合車牌格式）`)
    } else {
      ElMessage.info('圖片中未偵測到車牌')
    }
    void loadAll()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function closePresence(id: number) {
  await api.post(`/api/presence/${id}/close`)
  ElMessage.success('已結清離場')
  void loadAll()
}

const unsubs: Array<() => void> = []

onMounted(() => {
  void loadAll()
  timer = window.setInterval(() => {
    nowTick.value = Date.now()
  }, 500)
  unsubs.push(
    wsHub.on('access_event', () => void loadAll()),
    wsHub.on('access_event_updated', () => void loadAll()),
    wsHub.on('lane_status', (st) => {
      const target = lanes.value.find((l) => l.id === Number(st.lane_id))
      if (target) {
        target.status = st as unknown as Lane['status']
      }
    }),
  )
})

onUnmounted(() => {
  if (timer !== null) clearInterval(timer)
  unsubs.forEach((u) => u())
})
</script>

<style scoped>
.stat-card {
  text-align: center;
}
.stat-label {
  font-size: 12px;
  color: #64748b;
  margin-bottom: 4px;
}
.stat-val {
  font-size: 24px;
  font-weight: 700;
}
.text-primary { color: #2563eb; }
.text-success { color: #16a34a; }
.text-danger { color: #dc2626; }
.lane-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.stream-wrap {
  position: relative;
  background: #111827;
  border-radius: 6px;
  overflow: hidden;
  aspect-ratio: 16 / 9;
}
.stream-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.gate-banner {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 16px;
  border-radius: 999px;
  font-weight: 600;
  color: #fff;
  font-size: 14px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
}
.gate-banner.ok { background: #16a34a; }
.gate-banner.err { background: #dc2626; }
.lane-tools {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
  flex-wrap: wrap;
}
</style>
