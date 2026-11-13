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
        <LaneCard :lane="lane" :now-tick="nowTick" @show-qr="showQr" @changed="loadAll" />
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
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import LaneCard from '../components/LaneCard.vue'
import MobileCameraQrDialog from '../components/MobileCameraQrDialog.vue'
import {
  api,
  CATEGORY_LABEL,
  DECISION_LABEL,
  DIRECTION_LABEL,
  fmtDateTime,
  VEHICLE_TYPE_LABEL,
  type AccessEvent,
  type Lane,
} from '../api'
import { useMonitorData } from '../composables/useMonitorData'

const router = useRouter()
const { enabledLanes, recentEvents, presence, stats, loadAll } = useMonitorData()
const activeTab = ref('events')
const previewEvent = ref<AccessEvent | null>(null)
// 開閘提示橫幅依此判斷是否已過期
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

async function closePresence(id: number) {
  await api.post(`/api/presence/${id}/close`)
  ElMessage.success('已結清離場')
  void loadAll()
}

onMounted(() => {
  timer = window.setInterval(() => {
    nowTick.value = Date.now()
  }, 500)
})

onUnmounted(() => {
  if (timer !== null) clearInterval(timer)
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
</style>
