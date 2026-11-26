<template>
  <div>
    <div class="page-header">
      <div>
        <div class="page-eyebrow">Alerts</div>
        <h2 class="page-title">警示中心</h2>
      </div>
      <div class="page-actions">
        <el-radio-group v-model="filterAck" @change="load">
          <el-radio-button :value="false">未處理</el-radio-button>
          <el-radio-button :value="true">已處理</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
        </el-radio-group>
        <el-button type="primary" plain @click="ackAll">全部標記已處理</el-button>
      </div>
    </div>

    <section class="type-stats" aria-label="警示類型統計">
      <div v-for="t in typeStats" :key="t.key" class="type-stat">
        <span class="type-stat-label">{{ t.label }}</span>
        <strong class="type-stat-val" :class="{ zero: t.count === 0 }">{{ t.count }}</strong>
      </div>
    </section>

    <el-card shadow="never">
      <el-skeleton v-if="!loaded" animated :rows="6" />
      <el-table v-else :data="alerts" stripe>
        <template #empty><EmptyState title="目前沒有警示" description="值班狀況一切正常" /></template>
        <el-table-column label="時間" width="165">
          <template #default="{ row }">{{ fmtDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="類型" width="120">
          <template #default="{ row }">
            <el-tag :type="row.type === 'BLACKLIST' ? 'danger' : 'warning'" size="small">
              {{ ALERT_TYPE_LABEL[row.type] || row.type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="車牌" width="130">
          <template #default="{ row }">
            <span v-if="row.plate_display" class="plate-badge">{{ row.plate_display }}</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="message" label="內容" min-width="240" />
        <el-table-column label="狀態" width="100">
          <template #default="{ row }">
            <el-tag :type="row.acknowledged ? 'info' : 'danger'" size="small">
              {{ row.acknowledged ? '已處理' : '未處理' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button v-if="!row.acknowledged" link type="primary" size="small" @click="ack(row.id)">
              標記已處理
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ALERT_TYPE_LABEL, api, fmtDateTime, type AlertItem } from '../api'
import { refreshPendingAndAlerts } from '../store'
import { wsHub } from '../ws'
import EmptyState from '../components/EmptyState.vue'

const filterAck = ref<boolean | 'all'>(false)
const alerts = ref<AlertItem[]>([])

// 依目前列表（受上方篩選影響）統計各類型筆數
const typeStats = computed(() =>
  Object.entries(ALERT_TYPE_LABEL).map(([key, label]) => ({
    key,
    label,
    count: alerts.value.filter((a) => a.type === key).length,
  })),
)

// 首次載入完成前顯示骨架屏
const loaded = ref(false)

async function load() {
  try {
    const qs = filterAck.value === 'all' ? '' : `&acknowledged=${filterAck.value}`
    const res = await api.get<{ items: AlertItem[] }>(`/api/alerts?page=1&page_size=100${qs}`)
    alerts.value = res.items
  } finally {
    loaded.value = true
  }
}

async function ack(id: number) {
  await api.post(`/api/alerts/${id}/ack`)
  ElMessage.success('已處理')
  await Promise.all([load(), refreshPendingAndAlerts()])
}

async function ackAll() {
  const res = await api.post<{ acknowledged: number }>('/api/alerts/ack-all')
  ElMessage.success(`已標記 ${res.acknowledged} 筆警示`)
  await Promise.all([load(), refreshPendingAndAlerts()])
}

const unsubs: Array<() => void> = []
onMounted(() => {
  void load()
  unsubs.push(
    wsHub.on('alert', () => void load()),
    wsHub.on('alerts_changed', () => void load()),
  )
})
onUnmounted(() => unsubs.forEach((u) => u()))
</script>

<style scoped>
.type-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: var(--cg-space-3);
  margin-bottom: var(--cg-space-4);
}
.type-stat {
  display: flex;
  flex-direction: column;
  gap: var(--cg-space-1);
  padding: var(--cg-space-3) var(--cg-space-4);
  background: var(--cg-surface);
  border: 1px solid var(--cg-hairline);
  border-radius: var(--cg-radius-lg);
}
.type-stat-label {
  font-size: var(--cg-text-xs);
  color: var(--cg-text-3);
}
.type-stat-val {
  font-family: var(--cg-font-serif);
  font-size: var(--cg-text-2xl);
  color: var(--cg-navy);
}
.type-stat-val.zero {
  color: var(--cg-text-3);
}
</style>
