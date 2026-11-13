<template>
  <div>
    <div class="page-header">
      <div>
        <h2 class="page-title">即時監控</h2>
      </div>
      <div class="page-actions">
        <el-button :icon="Refresh" @click="loadAll">重新整理</el-button>
      </div>
    </div>

    <!-- 今日統計 -->
    <section class="stat-grid" aria-label="今日統計">
      <component
        :is="s.to ? 'button' : 'div'"
        v-for="s in statItems"
        :key="s.label"
        class="stat-card"
        :class="[s.tone, { clickable: !!s.to }]"
        :type="s.to ? 'button' : undefined"
        @click="s.to && router.push(s.to)"
      >
        <div class="stat-label">{{ s.label }}</div>
        <div class="stat-val">
          {{ s.value }}
          <span v-if="s.extra" class="stat-extra">{{ s.extra }}</span>
        </div>
      </component>
    </section>

    <!-- 車道即時畫面 -->
    <section class="lane-grid" aria-label="車道即時畫面">
      <LaneCard
        v-for="lane in enabledLanes"
        :key="lane.id"
        :lane="lane"
        :now-tick="nowTick"
        @show-qr="showQr"
        @changed="loadAll"
      />
    </section>

    <!-- 即時紀錄 / 目前在場車輛 -->
    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="最新進出紀錄" name="events">
          <el-table :data="recentEvents" stripe>
            <template #empty><EmptyState title="今日尚無進出紀錄" description="車輛經過車道後會即時顯示在這裡" /></template>
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
                <span v-else class="text-muted">—</span>
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
            <el-table-column label="結果" width="120">
              <template #default="{ row }">
                <DecisionMark :decision="row.decision" />
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
          <el-table :data="presence" stripe>
            <template #empty><EmptyState title="目前沒有在場車輛" /></template>
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
      <div v-if="previewEvent" class="preview">
        <div class="preview-head">
          <span class="plate-badge lg">{{ previewEvent.plate_display || '無車牌' }}</span>
          <span class="text-muted mono">{{ fmtDateTime(previewEvent.occurred_at) }}</span>
        </div>
        <img v-if="previewEvent.plate_crop_url" :src="previewEvent.plate_crop_url" class="preview-crop" alt="車牌裁切" />
        <img v-if="previewEvent.snapshot_url" :src="previewEvent.snapshot_url" class="preview-snap" alt="現場截圖" />
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
import DecisionMark from '../components/DecisionMark.vue'
import EmptyState from '../components/EmptyState.vue'
import LaneCard from '../components/LaneCard.vue'
import MobileCameraQrDialog from '../components/MobileCameraQrDialog.vue'
import {
  api,
  CATEGORY_LABEL,
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

const statItems = computed(() => [
  { label: '今日進場', value: stats.today_in, tone: 'accent' },
  { label: '今日離場', value: stats.today_out, tone: '' },
  { label: '目前在場車輛', value: stats.onsite_vehicles, tone: 'success' },
  {
    label: '在場／逾時訪客',
    value: stats.onsite_visitors,
    extra: stats.overstay_visitors ? `逾時 ${stats.overstay_visitors}` : '',
    tone: stats.overstay_visitors ? 'danger' : '',
  },
  { label: '今日拒絕', value: stats.today_denied, tone: stats.today_denied ? 'danger' : '' },
  { label: '未處理警示', value: stats.unack_alerts, tone: stats.unack_alerts ? 'danger' : '', to: '/alerts' },
])

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
.stat-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: var(--cg-space-3);
  margin-bottom: var(--cg-space-5);
}
.stat-card {
  position: relative;
  padding: 18px 20px 16px;
  border-radius: var(--cg-radius-lg);
  border: 1px solid var(--cg-border);
  background: var(--cg-surface);
  box-shadow: var(--cg-shadow-sm);
  text-align: left;
  font: inherit;
  color: inherit;
  overflow: hidden;
  transition: box-shadow var(--cg-duration) var(--cg-ease), transform var(--cg-duration) var(--cg-ease),
    border-color var(--cg-duration) var(--cg-ease);
}
.stat-card::before {
  content: "";
  position: absolute;
  left: 20px;
  top: 0;
  width: 24px;
  height: 2px;
  border-radius: 0 0 2px 2px;
  background: var(--cg-border-strong);
}
.stat-card.accent::before { background: var(--cg-gold); }
.stat-card.success::before { background: var(--cg-success); }
.stat-card.danger::before { background: var(--cg-danger); }
.stat-card.clickable {
  cursor: pointer;
}
.stat-card.clickable:hover {
  border-color: var(--cg-gold);
  box-shadow: var(--cg-shadow-md);
  transform: translateY(-1px);
}
.stat-label {
  font-size: var(--cg-text-xs);
  letter-spacing: 0.12em;
  color: var(--cg-text-3);
}
.stat-val {
  margin-top: 8px;
  font-family: var(--cg-font-mono);
  font-variant-numeric: tabular-nums;
  font-size: 30px;
  font-weight: 600;
  line-height: 1.1;
  color: var(--cg-text);
}
.stat-card.success .stat-val { color: var(--cg-success-text); }
.stat-card.danger .stat-val { color: var(--cg-danger-text); }
.stat-extra {
  margin-left: 6px;
  font-family: var(--cg-font-sans);
  font-size: var(--cg-text-sm);
  font-weight: 500;
  color: var(--cg-danger-text);
}

.lane-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(460px, 1fr));
  gap: var(--cg-space-4);
  margin-bottom: var(--cg-space-5);
}

.preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--cg-space-3);
}
.preview-head {
  display: flex;
  align-items: center;
  gap: var(--cg-space-3);
}
.preview-crop {
  max-height: 70px;
  border-radius: var(--cg-radius-sm);
}
.preview-snap {
  width: 100%;
  border-radius: var(--cg-radius-md);
  background: var(--cg-media-bg);
}

@media (max-width: 1279px) {
  .stat-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
@media (max-width: 1100px) {
  .lane-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
