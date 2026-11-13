<template>
  <el-dialog
    :model-value="!!currentEvent"
    width="760px"
    class="pending-dialog"
    :close-on-click-modal="false"
    @close="dismiss"
  >
    <template #header>
      <div class="dlg-head">
        <span class="dlg-kicker"><el-icon><WarningFilled /></el-icon>待確認</span>
        <span class="dlg-title">未登記車輛</span>
      </div>
    </template>

    <transition name="fade-rise" mode="out-in">
      <div v-if="currentEvent" :key="currentEvent.id">
        <section class="evidence">
          <div class="media">
            <img v-if="currentEvent.snapshot_url" :src="currentEvent.snapshot_url" class="snap-img" alt="現場截圖" />
            <div v-else class="snap-img snap-empty">無現場截圖</div>
            <span class="media-tag">{{ currentEvent.lane_name || '車道' }} · {{ DIRECTION_LABEL[currentEvent.direction] || currentEvent.direction }}</span>
          </div>
          <div class="facts">
            <div class="plate-badge lg">{{ currentEvent.plate_display || currentEvent.plate }}</div>
            <img v-if="currentEvent.plate_crop_url" :src="currentEvent.plate_crop_url" class="crop-img" alt="車牌裁切" />
            <dl class="fact-list">
              <div><dt>車種</dt><dd>{{ VEHICLE_TYPE_LABEL[currentEvent.vehicle_type] || '未知' }}</dd></div>
              <div><dt>時間</dt><dd class="mono">{{ fmtDateTime(currentEvent.occurred_at) }}</dd></div>
              <div>
                <dt>辨識信心</dt>
                <dd class="mono" :class="{ 'text-warning': currentEvent.confidence < 0.85 }">
                  {{ (currentEvent.confidence * 100).toFixed(0) }}%
                </dd>
              </div>
            </dl>
          </div>
        </section>

        <section class="decision">
      <el-radio-group v-model="mode" size="large" class="mode-group">
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
        </section>
      </div>
    </transition>

    <template #footer>
      <div class="dlg-footer">
        <span class="queue text-muted">待處理佇列 <strong class="mono">{{ appState.pendingEvents.length }}</strong> 筆</span>
        <div class="footer-actions">
          <el-button size="large" @click="dismiss">稍後處理</el-button>
          <el-button
            size="large"
            class="confirm-btn"
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
import { WarningFilled } from '@element-plus/icons-vue'
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
.dlg-head {
  display: flex;
  align-items: center;
  gap: var(--cg-space-3);
}
.dlg-kicker {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 10px;
  border-radius: var(--cg-radius-pill);
  font-size: var(--cg-text-xs);
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--cg-warning-text);
  background: color-mix(in srgb, var(--cg-warning) 12%, transparent);
}
.dlg-title {
  font-family: var(--cg-font-serif);
  font-size: var(--cg-text-xl);
  font-weight: 600;
  letter-spacing: 0.06em;
}

.evidence {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
  gap: var(--cg-space-5);
  padding-bottom: var(--cg-space-5);
  border-bottom: 1px solid var(--cg-border);
}
.media {
  position: relative;
}
.snap-img {
  display: block;
  width: 100%;
  aspect-ratio: 16 / 10;
  object-fit: cover;
  border-radius: var(--cg-radius-md);
  background: var(--cg-media-bg);
}
.snap-empty {
  display: grid;
  place-items: center;
  color: var(--cg-side-text-dim);
  font-size: var(--cg-text-sm);
}
.media-tag {
  position: absolute;
  left: 10px;
  bottom: 10px;
  padding: 3px 10px;
  border-radius: var(--cg-radius-pill);
  font-size: var(--cg-text-xs);
  letter-spacing: 0.08em;
  color: var(--cg-overlay-text);
  background: var(--cg-overlay);
  backdrop-filter: blur(6px);
}
.facts {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--cg-space-3);
}
.crop-img {
  max-width: 100%;
  max-height: 64px;
  border-radius: var(--cg-radius-sm);
  border: 1px solid var(--cg-border);
  object-fit: contain;
  background: var(--cg-media-bg);
}
.fact-list {
  margin: 0;
  width: 100%;
  display: grid;
  gap: 8px;
}
.fact-list div {
  display: flex;
  justify-content: space-between;
  gap: var(--cg-space-3);
  padding-bottom: 8px;
  border-bottom: 1px dashed var(--cg-border);
}
.fact-list dt {
  font-size: var(--cg-text-sm);
  color: var(--cg-text-3);
  letter-spacing: 0.06em;
}
.fact-list dd {
  margin: 0;
  font-weight: 500;
  color: var(--cg-text);
}

.decision {
  padding-top: var(--cg-space-5);
}
.mode-group {
  display: flex;
  width: 100%;
  margin-bottom: var(--cg-space-4);
}
.mode-group :deep(.el-radio-button) {
  flex: 1;
}
.mode-group :deep(.el-radio-button__inner) {
  width: 100%;
}

.dlg-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--cg-space-3);
  width: 100%;
}
.footer-actions {
  display: flex;
  gap: var(--cg-space-3);
}
/* 主要按鈕：寬度固定，不因文案長短位移，降低誤觸 */
.confirm-btn {
  min-width: 200px;
}

@media (max-width: 820px) {
  .evidence {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
