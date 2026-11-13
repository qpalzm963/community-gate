<template>
  <div>
    <div class="page-header">
      <h2 class="page-title">進出紀錄查詢</h2>
      <div style="display: flex; gap: 8px">
        <el-button @click="doExport('csv')">匯出 CSV</el-button>
        <el-button type="primary" @click="doExport('xlsx')">匯出 Excel (.xlsx)</el-button>
      </div>
    </div>

    <el-card shadow="never" style="margin-bottom: 14px">
      <el-form inline>
        <el-form-item label="日期">
          <el-date-picker
            v-model="filters.dates"
            type="daterange"
            range-separator="至"
            start-placeholder="開始"
            end-placeholder="結束"
            value-format="YYYY-MM-DD"
            clearable
          />
        </el-form-item>
        <el-form-item label="車牌">
          <el-input v-model="filters.plate" placeholder="關鍵字" clearable style="width: 130px" @keyup.enter="search" />
        </el-form-item>
        <el-form-item label="車道">
          <el-select v-model="filters.lane_id" clearable placeholder="全部" style="width: 120px">
            <el-option v-for="l in lanes" :key="l.id" :label="l.name" :value="l.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="車種">
          <el-select v-model="filters.vehicle_type" clearable placeholder="全部" style="width: 100px">
            <el-option value="CAR" label="汽車" />
            <el-option value="MOTO" label="機車" />
            <el-option value="UNKNOWN" label="未知" />
          </el-select>
        </el-form-item>
        <el-form-item label="類別">
          <el-select v-model="filters.category" clearable placeholder="全部" style="width: 110px">
            <el-option v-for="(lbl, k) in CATEGORY_LABEL" :key="k" :label="lbl" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item label="結果">
          <el-select v-model="filters.decision" clearable placeholder="全部" style="width: 110px">
            <el-option v-for="(lbl, k) in DECISION_LABEL" :key="k" :label="lbl" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="search">查詢</el-button>
          <el-button @click="reset">重設</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <el-table :data="items" stripe>
        <el-table-column label="時間" width="165">
          <template #default="{ row }">{{ fmtDateTime(row.occurred_at) }}</template>
        </el-table-column>
        <el-table-column prop="lane_name" label="車道" width="110" />
        <el-table-column label="方向" width="70">
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
          <template #default="{ row }">{{ CATEGORY_LABEL[row.category] }}</template>
        </el-table-column>
        <el-table-column label="處理結果" width="95">
          <template #default="{ row }">{{ DECISION_LABEL[row.decision] }}</template>
        </el-table-column>
        <el-table-column prop="household_unit" label="戶別" width="100" />
        <el-table-column label="信心" width="70">
          <template #default="{ row }">{{ row.confidence ? `${(row.confidence * 100).toFixed(0)}%` : '—' }}</template>
        </el-table-column>
        <el-table-column prop="operator_name" label="操作人" width="95" />
        <el-table-column prop="note" label="備註" min-width="140" show-overflow-tooltip />
        <el-table-column label="截圖" width="85" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.snapshot_url" link type="primary" size="small" @click="preview = row">檢視</el-button>
            <span v-else style="color: #94a3b8">—</span>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 14px; display: flex; justify-content: flex-end">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @change="load"
        />
      </div>
    </el-card>

    <el-dialog v-model="previewVisible" title="進出截圖" width="700px">
      <div v-if="preview" style="text-align: center">
        <div style="margin-bottom: 10px">
          <span class="plate-badge lg">{{ preview.plate_display || '無車牌' }}</span>
          <span style="margin-left: 12px; color: #64748b">{{ fmtDateTime(preview.occurred_at) }}</span>
        </div>
        <img v-if="preview.plate_crop_url" :src="preview.plate_crop_url" style="max-height: 70px; margin-bottom: 10px" />
        <img v-if="preview.snapshot_url" :src="preview.snapshot_url" style="width: 100%; border-radius: 6px" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
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

const lanes = ref<Lane[]>([])
const items = ref<AccessEvent[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const preview = ref<AccessEvent | null>(null)
const previewVisible = computed({
  get: () => !!preview.value,
  set: (v) => {
    if (!v) preview.value = null
  },
})

const filters = reactive({
  dates: null as [string, string] | null,
  plate: '',
  lane_id: undefined as number | undefined,
  vehicle_type: '',
  category: '',
  decision: '',
})

function queryString(withPage = true) {
  const params = new URLSearchParams()
  if (filters.dates) {
    params.set('start', filters.dates[0])
    params.set('end', filters.dates[1])
  }
  if (filters.plate) params.set('plate', filters.plate)
  if (filters.lane_id) params.set('lane_id', String(filters.lane_id))
  if (filters.vehicle_type) params.set('vehicle_type', filters.vehicle_type)
  if (filters.category) params.set('category', filters.category)
  if (filters.decision) params.set('decision', filters.decision)
  if (withPage) {
    params.set('page', String(page.value))
    params.set('page_size', String(pageSize.value))
  }
  return params.toString()
}

async function load() {
  const res = await api.get<{ total: number; items: AccessEvent[] }>(`/api/events?${queryString(true)}`)
  total.value = res.total
  items.value = res.items
}

function search() {
  page.value = 1
  void load()
}

function reset() {
  filters.dates = null
  filters.plate = ''
  filters.lane_id = undefined
  filters.vehicle_type = ''
  filters.category = ''
  filters.decision = ''
  search()
}

function doExport(format: 'csv' | 'xlsx') {
  const qs = queryString(false)
  window.open(`/api/events/export?format=${format}${qs ? '&' + qs : ''}`, '_blank')
}

onMounted(async () => {
  lanes.value = await api.get<Lane[]>('/api/lanes')
  await load()
})
</script>
