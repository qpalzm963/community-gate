<template>
  <div>
    <div class="page-header">
      <h2 class="page-title">警示中心</h2>
      <div class="page-actions">
        <el-radio-group v-model="filterAck" @change="load">
          <el-radio-button :value="false">未處理</el-radio-button>
          <el-radio-button :value="true">已處理</el-radio-button>
          <el-radio-button value="all">全部</el-radio-button>
        </el-radio-group>
        <el-button type="primary" plain @click="ackAll">全部標記已處理</el-button>
      </div>
    </div>

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
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ALERT_TYPE_LABEL, api, fmtDateTime, type AlertItem } from '../api'
import { refreshPendingAndAlerts } from '../store'
import { wsHub } from '../ws'
import EmptyState from '../components/EmptyState.vue'

const filterAck = ref<boolean | 'all'>(false)
const alerts = ref<AlertItem[]>([])

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
