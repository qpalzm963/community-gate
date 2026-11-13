<template>
  <el-dialog
    :model-value="!!currentEvent"
    title="未登記車輛待確認"
    width="620px"
    :close-on-click-modal="false"
    @close="dismiss"
  >
    <template v-if="currentEvent">
      <el-alert
        type="warning"
        :closable="false"
        style="margin-bottom: 14px"
        :title="`${currentEvent.lane_name || '車道'}（${DIRECTION_LABEL[currentEvent.direction] || currentEvent.direction}）偵測到未登記車輛`"
      />

      <div class="pending-head">
        <div class="plate-info">
          <div class="plate-badge lg">{{ currentEvent.plate_display || currentEvent.plate }}</div>
          <div class="meta">
            <span>車種：{{ VEHICLE_TYPE_LABEL[currentEvent.vehicle_type] || '未知' }}</span>
            <span>時間：{{ fmtDateTime(currentEvent.occurred_at) }}</span>
            <span>信心值：{{ (currentEvent.confidence * 100).toFixed(0) }}%</span>
          </div>
          <img
            v-if="currentEvent.plate_crop_url"
            :src="currentEvent.plate_crop_url"
            class="crop-img"
            alt="車牌裁切"
          />
        </div>
        <img
          v-if="currentEvent.snapshot_url"
          :src="currentEvent.snapshot_url"
          class="snap-img"
          alt="現場截圖"
        />
      </div>

      <el-divider />

      <el-radio-group v-model="mode" style="margin-bottom: 14px">
        <el-radio-button value="once">放行一次</el-radio-button>
        <el-radio-button value="visitor">登記為訪客並放行</el-radio-button>
        <el-radio-button value="deny">拒絕進入</el-radio-button>
      </el-radio-group>

      <el-form v-if="mode === 'visitor'" label-width="90px" size="default">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="拜訪戶別" required>
              <el-select v-model="visitorForm.household_id" filterable placeholder="選擇戶別" style="width: 100%">
                <el-option v-for="h in households" :key="h.id" :label="`${h.unit_no} ${h.owner_name}`" :value="h.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="訪客姓名" required>
              <el-input v-model="visitorForm.name" placeholder="例如：林先生 / 宅配" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="聯絡電話">
              <el-input v-model="visitorForm.phone" placeholder="選填" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="車種">
              <el-radio-group v-model="visitorForm.vehicle_type">
                <el-radio value="CAR">汽車</el-radio>
                <el-radio value="MOTO">機車</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="授權時數">
              <el-select v-model="hours" style="width: 100%">
                <el-option :value="1" label="1 小時" />
                <el-option :value="2" label="2 小時" />
                <el-option :value="4" label="4 小時" />
                <el-option :value="8" label="8 小時" />
                <el-option :value="24" label="24 小時" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="事由">
              <el-input v-model="visitorForm.purpose" placeholder="例如：親友來訪 / 維修" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <el-form v-else label-width="90px">
        <el-form-item label="備註">
          <el-input v-model="note" :placeholder="mode === 'deny' ? '例如：未事先聯繫住戶' : '例如：快遞臨停 / 住戶電話確認'" />
        </el-form-item>
      </el-form>
    </template>

    <template #footer>
      <div style="display: flex; justify-content: space-between; align-items: center; width: 100%">
        <span style="color: #64748b; font-size: 13px">
          待處理佇列：{{ appState.pendingEvents.length }} 筆
        </span>
        <div>
          <el-button @click="dismiss">稍後處理</el-button>
          <el-button
            :type="mode === 'deny' ? 'danger' : 'primary'"
            :loading="submitting"
            @click="submit"
          >
            {{ mode === 'deny' ? '確認拒絕' : mode === 'visitor' ? '建立訪客並開閘' : '確認放行並開閘' }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  api,
  DIRECTION_LABEL,
  fmtDateTime,
  toLocalIso,
  VEHICLE_TYPE_LABEL,
  type Household,
  type Visitor,
} from '../api'
import { appState } from '../store'

const dismissedIds = ref(new Set<number>())
const mode = ref<'once' | 'visitor' | 'deny'>('once')
const note = ref('')
const hours = ref(4)
const submitting = ref(false)
const households = ref<Household[]>([])

const visitorForm = reactive({
  household_id: undefined as number | undefined,
  name: '',
  phone: '',
  vehicle_type: 'CAR' as 'CAR' | 'MOTO',
  purpose: '',
})

const currentEvent = computed(() => appState.pendingEvents.find((e) => !dismissedIds.value.has(e.id)) ?? null)

watch(currentEvent, async (ev) => {
  if (!ev) return
  mode.value = 'once'
  note.value = ''
  visitorForm.name = ''
  visitorForm.phone = ''
  visitorForm.purpose = ''
  visitorForm.vehicle_type = ev.vehicle_type === 'MOTO' ? 'MOTO' : 'CAR'
  if (households.value.length === 0) {
    try {
      households.value = await api.get<Household[]>('/api/households')
    } catch {
      // ignore
    }
  }
})

function dismiss() {
  if (currentEvent.value) {
    dismissedIds.value.add(currentEvent.value.id)
  }
}

async function submit() {
  const ev = currentEvent.value
  if (!ev) return
  submitting.value = true
  try {
    if (mode.value === 'visitor') {
      if (!visitorForm.household_id || !visitorForm.name.trim()) {
        ElMessage.warning('請選擇拜訪戶別並填寫訪客姓名')
        return
      }
      const start = new Date()
      const end = new Date(start.getTime() + hours.value * 3600 * 1000)
      const vis = await api.post<Visitor>('/api/visitors', {
        household_id: visitorForm.household_id,
        name: visitorForm.name.trim(),
        phone: visitorForm.phone.trim(),
        plate: ev.plate,
        vehicle_type: visitorForm.vehicle_type,
        purpose: visitorForm.purpose.trim(),
        authorized_from: toLocalIso(start),
        authorized_until: toLocalIso(end),
        source: 'WALK_IN',
      })
      await api.post(`/api/events/${ev.id}/decision`, {
        action: 'allow',
        visitor_id: vis.id,
        note: note.value.trim(),
      })
      ElMessage.success(`已登記訪客 ${vis.name} 並開閘`)
    } else {
      await api.post(`/api/events/${ev.id}/decision`, {
        action: mode.value === 'deny' ? 'deny' : 'allow',
        note: note.value.trim(),
      })
      ElMessage.success(mode.value === 'deny' ? '已拒絕進入' : '已放行並開閘')
    }
    appState.pendingEvents = appState.pendingEvents.filter((p) => p.id !== ev.id)
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.pending-head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}
.plate-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 13px;
  color: #475569;
}
.crop-img {
  max-width: 180px;
  max-height: 70px;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
  object-fit: contain;
}
.snap-img {
  width: 260px;
  height: 160px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
}
</style>
