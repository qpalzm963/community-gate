<template>
  <div>
    <div class="page-header">
      <h2 class="page-title">黑名單管理</h2>
      <div style="display: flex; gap: 8px">
        <el-input v-model="q" placeholder="搜尋車牌 / 原因" clearable style="width: 220px" @input="load" />
        <el-button type="danger" @click="openForm()">加入黑名單</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <el-table :data="rows" stripe>
        <el-table-column label="車牌" width="150">
          <template #default="{ row }">
            <span class="plate-badge">{{ row.plate_display }}</span>
          </template>
        </el-table-column>
        <el-table-column label="車種" width="90">
          <template #default="{ row }">{{ VEHICLE_TYPE_LABEL[row.vehicle_type] }}</template>
        </el-table-column>
        <el-table-column prop="reason" label="原因" min-width="200" />
        <el-table-column label="狀態" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'danger' : 'info'" size="small">
              {{ row.is_active ? '生效中' : '已停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="建立時間" width="170">
          <template #default="{ row }">{{ fmtDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="130">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openForm(row)">編輯</el-button>
            <el-button link type="danger" size="small" @click="del(row)">刪除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dlg" :title="form.id ? '編輯黑名單' : '加入黑名單'" width="440px">
      <el-form label-width="80px">
        <el-form-item label="車牌" required>
          <el-input v-model="form.plate" placeholder="例：ABC-1234" />
        </el-form-item>
        <el-form-item label="車種">
          <el-radio-group v-model="form.vehicle_type">
            <el-radio value="UNKNOWN">不限</el-radio>
            <el-radio value="CAR">汽車</el-radio>
            <el-radio value="MOTO">機車</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="原因">
          <el-input v-model="form.reason" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="生效中">
          <el-switch v-model="form.is_active" />
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
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, fmtDateTime, VEHICLE_TYPE_LABEL, type BlacklistEntry, type VehicleType } from '../api'

const q = ref('')
const rows = ref<BlacklistEntry[]>([])
const dlg = ref(false)
const form = reactive({ id: 0, plate: '', vehicle_type: 'UNKNOWN' as VehicleType, reason: '', is_active: true })

async function load() {
  rows.value = await api.get<BlacklistEntry[]>(`/api/blacklist?q=${encodeURIComponent(q.value)}`)
}

function openForm(b?: BlacklistEntry) {
  form.id = b?.id ?? 0
  form.plate = b?.plate_display ?? ''
  form.vehicle_type = b?.vehicle_type ?? 'UNKNOWN'
  form.reason = b?.reason ?? ''
  form.is_active = b?.is_active ?? true
  dlg.value = true
}

async function save() {
  try {
    const payload = { plate: form.plate, vehicle_type: form.vehicle_type, reason: form.reason, is_active: form.is_active }
    if (form.id) await api.put(`/api/blacklist/${form.id}`, payload)
    else await api.post('/api/blacklist', payload)
    dlg.value = false
    ElMessage.success('已儲存')
    await load()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function del(b: BlacklistEntry) {
  await ElMessageBox.confirm(`確定從黑名單移除 ${b.plate_display}？`, '確認', { type: 'warning' })
  await api.del(`/api/blacklist/${b.id}`)
  ElMessage.success('已刪除')
  await load()
}

onMounted(() => void load())
</script>
