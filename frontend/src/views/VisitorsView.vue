<template>
  <div>
    <div class="page-header">
      <div>
        <div class="page-eyebrow">Visitors</div>
        <h2 class="page-title">訪客管理</h2>
      </div>
      <div class="page-actions">
        <el-input v-model="q" placeholder="搜尋姓名 / 車牌 / 戶別" clearable style="width: 220px" @input="load" />
        <el-button type="primary" @click="openForm(undefined, 'RESERVATION')">預約登記</el-button>
        <el-button type="success" @click="openForm(undefined, 'WALK_IN')">現場登記</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-tabs v-model="scope" @tab-change="load">
        <el-tab-pane label="今日訪客" name="today" />
        <el-tab-pane label="目前在場" name="onsite" />
        <el-tab-pane label="逾時未離場" name="overstay" />
        <el-tab-pane label="即將來訪" name="upcoming" />
        <el-tab-pane label="全部紀錄" name="all" />
      </el-tabs>

      <el-skeleton v-if="!loaded" animated :rows="6" />

      <el-table v-else :data="visitors" stripe>

        <template #empty><EmptyState title="這個分類目前沒有訪客" /></template>
        <el-table-column prop="household_unit" label="拜訪戶別" width="110" />
        <el-table-column prop="name" label="訪客姓名" width="110" />
        <el-table-column prop="phone" label="電話" width="120" />
        <el-table-column label="車牌" width="130">
          <template #default="{ row }">
            <span v-if="row.plate_display" class="plate-badge">{{ row.plate_display }}</span>
            <span v-else class="text-muted">步行／無車</span>
          </template>
        </el-table-column>
        <el-table-column label="車種" width="75">
          <template #default="{ row }">{{ row.plate ? VEHICLE_TYPE_LABEL[row.vehicle_type] : '—' }}</template>
        </el-table-column>
        <el-table-column prop="purpose" label="事由" min-width="110" />
        <el-table-column label="授權時段" width="290">
          <template #default="{ row }">
            {{ fmtDateTime(row.authorized_from).slice(5, 16) }} ～ {{ fmtDateTime(row.authorized_until).slice(5, 16) }}
          </template>
        </el-table-column>
        <el-table-column label="狀態" width="105">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ VISITOR_STATUS_LABEL[row.status] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'RESERVED'"
              link
              type="success"
              size="small"
              @click="checkin(row)"
            >
              標記入場
            </el-button>
            <el-button
              v-if="row.status === 'ENTERED' || row.status === 'OVERSTAY'"
              link
              type="warning"
              size="small"
              @click="checkout(row)"
            >
              標記離場
            </el-button>
            <el-button link type="primary" size="small" @click="openForm(row)">編輯</el-button>
            <el-button
              v-if="row.status === 'RESERVED'"
              link
              type="danger"
              size="small"
              @click="cancel(row)"
            >
              取消
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dlg" :title="form.id ? '編輯訪客' : form.source === 'WALK_IN' ? '現場訪客登記' : '預約訪客登記'" width="540px">
      <el-form label-width="95px">
        <el-form-item label="拜訪戶別" required>
          <el-select v-model="form.household_id" filterable placeholder="選擇戶別" style="width: 100%">
            <el-option v-for="h in households" :key="h.id" :label="`${h.unit_no} ${h.owner_name}`" :value="h.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="訪客姓名" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="聯絡電話">
          <el-input v-model="form.phone" placeholder="選填" />
        </el-form-item>
        <el-form-item label="車牌號碼">
          <el-input v-model="form.plate" placeholder="步行訪客可留空，例：ABC-1234" />
        </el-form-item>
        <el-form-item label="車種">
          <el-radio-group v-model="form.vehicle_type">
            <el-radio value="CAR">汽車</el-radio>
            <el-radio value="MOTO">機車</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="事由">
          <el-input v-model="form.purpose" placeholder="親友來訪 / 裝修 / 外送..." />
        </el-form-item>
        <el-form-item label="授權時段" required>
          <el-date-picker
            v-model="timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="開始時間"
            end-placeholder="結束時間"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg = false">取消</el-button>
        <el-button type="primary" @click="save">儲存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  api,
  fmtDateTime,
  toLocalIso,
  VEHICLE_TYPE_LABEL,
  VISITOR_STATUS_LABEL,
  type Household,
  type Visitor,
} from '../api'
import { wsHub } from '../ws'
import EmptyState from '../components/EmptyState.vue'

const scope = ref('today')
const q = ref('')
const visitors = ref<Visitor[]>([])
const households = ref<Household[]>([])
const dlg = ref(false)
const timeRange = ref<[string, string] | null>(null)

const form = reactive({
  id: 0,
  household_id: undefined as number | undefined,
  name: '',
  phone: '',
  plate: '',
  vehicle_type: 'CAR' as 'CAR' | 'MOTO',
  purpose: '',
  source: 'RESERVATION' as 'RESERVATION' | 'WALK_IN',
})

function statusTag(s: string) {
  if (s === 'ENTERED') return 'success'
  if (s === 'OVERSTAY') return 'danger'
  if (s === 'RESERVED') return 'primary'
  return 'info'
}

// 首次載入完成前顯示骨架屏
const loaded = ref(false)

async function load() {
  try {
    const [list, hh] = await Promise.all([
      api.get<Visitor[]>(`/api/visitors?scope=${scope.value}&q=${encodeURIComponent(q.value)}`),
      households.value.length ? Promise.resolve(households.value) : api.get<Household[]>('/api/households'),
    ])
    visitors.value = list
    households.value = hh
  } finally {
    loaded.value = true
  }
}

function openForm(v?: Visitor, source: 'RESERVATION' | 'WALK_IN' = 'RESERVATION') {
  form.id = v?.id ?? 0
  form.household_id = v?.household_id
  form.name = v?.name ?? ''
  form.phone = v?.phone ?? ''
  form.plate = v?.plate_display ?? ''
  form.vehicle_type = v?.vehicle_type ?? 'CAR'
  form.purpose = v?.purpose ?? ''
  form.source = v?.source ?? source
  if (v) {
    timeRange.value = [v.authorized_from.slice(0, 19), v.authorized_until.slice(0, 19)]
  } else {
    const start = new Date()
    const end = new Date(start.getTime() + 4 * 3600 * 1000)
    timeRange.value = [toLocalIso(start), toLocalIso(end)]
  }
  dlg.value = true
}

async function save() {
  if (!form.household_id || !form.name.trim() || !timeRange.value) {
    ElMessage.warning('請填寫拜訪戶別、姓名與授權時段')
    return
  }
  try {
    const payload = {
      household_id: form.household_id,
      name: form.name.trim(),
      phone: form.phone.trim(),
      plate: form.plate.trim(),
      vehicle_type: form.vehicle_type,
      purpose: form.purpose.trim(),
      authorized_from: timeRange.value[0],
      authorized_until: timeRange.value[1],
      source: form.source,
    }
    if (form.id) await api.put(`/api/visitors/${form.id}`, payload)
    else await api.post('/api/visitors', payload)
    dlg.value = false
    ElMessage.success('已儲存')
    await load()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function checkin(v: Visitor) {
  await api.post(`/api/visitors/${v.id}/checkin`)
  ElMessage.success('已標記入場')
  await load()
}

async function checkout(v: Visitor) {
  await api.post(`/api/visitors/${v.id}/checkout`)
  ElMessage.success('已標記離場')
  await load()
}

async function cancel(v: Visitor) {
  await ElMessageBox.confirm(`確定取消 ${v.name} 的訪客授權？`, '確認', { type: 'warning' })
  await api.post(`/api/visitors/${v.id}/cancel`)
  ElMessage.success('已取消')
  await load()
}

let unsub: (() => void) | null = null
onMounted(() => {
  void load()
  unsub = wsHub.on('visitors_changed', () => void load())
})
onUnmounted(() => unsub?.())
</script>
