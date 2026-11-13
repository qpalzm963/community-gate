<template>
  <div>
    <div class="page-header">
      <h2 class="page-title">住戶與車輛白名單</h2>
      <div class="page-actions">
        <el-input v-model="q" placeholder="搜尋戶別 / 住戶 / 車牌" clearable style="width: 240px" @input="load" />
        <el-button type="primary" @click="openHousehold()">新增戶別</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-skeleton v-if="!loaded" animated :rows="6" />
      <el-table v-else :data="households" row-key="id" default-expand-all>
        <template #empty><EmptyState title="尚未登記任何住戶" description="點右上角「新增戶別」開始建立白名單" /></template>
        <el-table-column type="expand">
          <template #default="{ row }">
            <div style="padding: 4px 20px 12px">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
                <strong>登記車輛（{{ row.vehicles?.length || 0 }}）</strong>
                <el-button size="small" type="primary" plain @click="openVehicle(row)">+ 新增車輛</el-button>
              </div>
              <el-table :data="row.vehicles || []" size="small" border>
                <el-table-column label="車牌" width="130">
                  <template #default="{ row: v }">
                    <span class="plate-badge">{{ v.plate_display }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="車種" width="80">
                  <template #default="{ row: v }">{{ VEHICLE_TYPE_LABEL[v.vehicle_type] }}</template>
                </el-table-column>
                <el-table-column label="有效期" width="210">
                  <template #default="{ row: v }">
                    {{ v.valid_from || '不限' }} ～ {{ v.valid_until || '永久' }}
                  </template>
                </el-table-column>
                <el-table-column label="狀態" width="80">
                  <template #default="{ row: v }">
                    <el-tag :type="v.is_active ? 'success' : 'info'" size="small">
                      {{ v.is_active ? '啟用' : '停用' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="note" label="備註" min-width="120" />
                <el-table-column label="操作" width="130">
                  <template #default="{ row: v }">
                    <el-button link type="primary" size="small" @click="openVehicle(row, v)">編輯</el-button>
                    <el-button link type="danger" size="small" @click="delVehicle(v)">刪除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="unit_no" label="戶別" width="140" />
        <el-table-column prop="owner_name" label="住戶姓名" width="130" />
        <el-table-column prop="phone" label="電話" width="140" />
        <el-table-column prop="vehicle_count" label="車輛數" width="90" />
        <el-table-column prop="note" label="備註" min-width="160" />
        <el-table-column label="操作" width="180">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openVehicle(row)">加車</el-button>
            <el-button link type="primary" size="small" @click="openHousehold(row)">編輯</el-button>
            <el-button link type="danger" size="small" @click="delHousehold(row)">刪除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 戶別對話框 -->
    <el-dialog v-model="hhDlg" :title="hhForm.id ? '編輯戶別' : '新增戶別'" width="440px">
      <el-form label-width="85px">
        <el-form-item label="戶別" required>
          <el-input v-model="hhForm.unit_no" placeholder="例：A棟5F-2" />
        </el-form-item>
        <el-form-item label="住戶姓名">
          <el-input v-model="hhForm.owner_name" />
        </el-form-item>
        <el-form-item label="聯絡電話">
          <el-input v-model="hhForm.phone" />
        </el-form-item>
        <el-form-item label="備註">
          <el-input v-model="hhForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="hhDlg = false">取消</el-button>
        <el-button type="primary" @click="saveHousehold">儲存</el-button>
      </template>
    </el-dialog>

    <!-- 車輛對話框 -->
    <el-dialog v-model="vehDlg" :title="vehForm.id ? '編輯車輛' : '新增住戶車輛'" width="460px">
      <el-form label-width="90px">
        <el-form-item label="戶別">
          <el-input :model-value="vehForm.unit_no" disabled />
        </el-form-item>
        <el-form-item label="車牌號碼" required>
          <el-input v-model="vehForm.plate" placeholder="例：ABC-1234 或 123-XYZ" />
        </el-form-item>
        <el-form-item label="車種">
          <el-radio-group v-model="vehForm.vehicle_type">
            <el-radio value="CAR">汽車</el-radio>
            <el-radio value="MOTO">機車</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="有效起日">
          <el-date-picker v-model="vehForm.valid_from" type="date" value-format="YYYY-MM-DD" placeholder="可不填" clearable />
        </el-form-item>
        <el-form-item label="有效迄日">
          <el-date-picker v-model="vehForm.valid_until" type="date" value-format="YYYY-MM-DD" placeholder="可不填（永久）" clearable />
        </el-form-item>
        <el-form-item label="啟用">
          <el-switch v-model="vehForm.is_active" />
        </el-form-item>
        <el-form-item label="備註">
          <el-input v-model="vehForm.note" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="vehDlg = false">取消</el-button>
        <el-button type="primary" @click="saveVehicle">儲存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, VEHICLE_TYPE_LABEL, type Household, type ResidentVehicle } from '../api'
import EmptyState from '../components/EmptyState.vue'

const q = ref('')
const households = ref<Household[]>([])

const hhDlg = ref(false)
const hhForm = reactive({ id: 0, unit_no: '', owner_name: '', phone: '', note: '' })

const vehDlg = ref(false)
const vehForm = reactive({
  id: 0,
  household_id: 0,
  unit_no: '',
  plate: '',
  vehicle_type: 'CAR' as 'CAR' | 'MOTO',
  valid_from: null as string | null,
  valid_until: null as string | null,
  is_active: true,
  note: '',
})

// 首次載入完成前顯示骨架屏
const loaded = ref(false)

async function load() {
  try {
    households.value = await api.get<Household[]>(`/api/households?q=${encodeURIComponent(q.value)}`)
  } finally {
    loaded.value = true
  }
}

function openHousehold(h?: Household) {
  hhForm.id = h?.id ?? 0
  hhForm.unit_no = h?.unit_no ?? ''
  hhForm.owner_name = h?.owner_name ?? ''
  hhForm.phone = h?.phone ?? ''
  hhForm.note = h?.note ?? ''
  hhDlg.value = true
}

async function saveHousehold() {
  try {
    const payload = { unit_no: hhForm.unit_no, owner_name: hhForm.owner_name, phone: hhForm.phone, note: hhForm.note }
    if (hhForm.id) await api.put(`/api/households/${hhForm.id}`, payload)
    else await api.post('/api/households', payload)
    hhDlg.value = false
    ElMessage.success('已儲存')
    await load()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function delHousehold(h: Household) {
  await ElMessageBox.confirm(`確定刪除戶別 ${h.unit_no} 及其名下車輛？`, '確認刪除', { type: 'warning' })
  try {
    await api.del(`/api/households/${h.id}`)
    ElMessage.success('已刪除')
    await load()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

function openVehicle(h: Household, v?: ResidentVehicle) {
  vehForm.id = v?.id ?? 0
  vehForm.household_id = h.id
  vehForm.unit_no = h.unit_no
  vehForm.plate = v?.plate_display ?? ''
  vehForm.vehicle_type = v?.vehicle_type ?? 'CAR'
  vehForm.valid_from = v?.valid_from ?? null
  vehForm.valid_until = v?.valid_until ?? null
  vehForm.is_active = v?.is_active ?? true
  vehForm.note = v?.note ?? ''
  vehDlg.value = true
}

async function saveVehicle() {
  try {
    const payload = {
      household_id: vehForm.household_id,
      plate: vehForm.plate,
      vehicle_type: vehForm.vehicle_type,
      valid_from: vehForm.valid_from || null,
      valid_until: vehForm.valid_until || null,
      is_active: vehForm.is_active,
      note: vehForm.note,
    }
    if (vehForm.id) await api.put(`/api/vehicles/${vehForm.id}`, payload)
    else await api.post('/api/vehicles', payload)
    vehDlg.value = false
    ElMessage.success('已儲存')
    await load()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function delVehicle(v: ResidentVehicle) {
  await ElMessageBox.confirm(`確定刪除車輛 ${v.plate_display}？`, '確認刪除', { type: 'warning' })
  await api.del(`/api/vehicles/${v.id}`)
  ElMessage.success('已刪除')
  await load()
}

onMounted(() => void load())
</script>
