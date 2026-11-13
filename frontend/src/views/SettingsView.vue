<template>
  <div>
    <div class="page-header">
      <div>
        <div class="page-eyebrow">Settings</div>
        <h2 class="page-title">系統設定</h2>
      </div>
    </div>

    <el-tabs v-model="tab">
      <!-- 車道與攝影機 / 柵欄 -->
      <el-tab-pane label="車道與硬體" name="lanes">
        <el-card shadow="never">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px">
            <span class="text-muted text-sm">
              手機測試串流範例：Android IP Webcam <code>http://手機IP:8080/video</code>、iPhone DroidCam
              <code>http://手機IP:4747/video</code>；正式機台用 <code>rtsp://...</code> 或本機測試影片路徑。
            </span>
            <el-button type="primary" @click="openLane()">新增車道</el-button>
          </div>
          <el-table :data="lanes" stripe>
            <el-table-column prop="name" label="車道名稱" width="130" />
            <el-table-column label="方向" width="80">
              <template #default="{ row }">{{ DIRECTION_LABEL[row.direction] }}</template>
            </el-table-column>
            <el-table-column label="車種" width="110">
              <template #default="{ row }">{{ VEHICLE_TYPE_LABEL[row.vehicle_types] }}</template>
            </el-table-column>
            <el-table-column prop="source_url" label="攝影機來源" min-width="210" show-overflow-tooltip />
            <el-table-column label="柵欄驅動" width="130">
              <template #default="{ row }">{{ driverLabel(row.gate_driver) }}</template>
            </el-table-column>
            <el-table-column label="狀態" width="110">
              <template #default="{ row }">
                <el-tag :type="row.enabled ? (row.status?.online ? 'success' : 'warning') : 'info'" size="small">
                  {{ !row.enabled ? '停用' : row.status?.online ? '連線中' : '離線' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="280">
              <template #default="{ row }">
                <el-button link type="warning" size="small" @click="showQr(row)">📱 手機鏡頭</el-button>
                <el-button link type="success" size="small" @click="testGate(row)">測試開閘</el-button>
                <el-button link type="primary" size="small" @click="openLane(row)">設定</el-button>
                <el-button link type="danger" size="small" @click="delLane(row)">刪除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- 系統參數 -->
      <el-tab-pane label="辨識與保留參數" name="params">
        <el-card shadow="never" style="max-width: 720px">
          <el-form label-width="240px">
            <el-form-item v-for="m in settingMeta" :key="m.key" :label="m.description">
              <el-switch v-if="m.type === 'bool'" v-model="settingValues[m.key]" />
              <el-input-number
                v-else-if="m.type === 'int' || m.type === 'float'"
                v-model="settingValues[m.key]"
                :min="m.min ?? undefined"
                :max="m.max ?? undefined"
                :step="m.type === 'float' ? 0.1 : 1"
              />
              <el-input v-else v-model="settingValues[m.key]" style="max-width: 280px" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingSettings" @click="saveSettings">儲存設定（即時生效）</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never" style="max-width: 720px; margin-top: 16px">
          <el-form label-width="240px">
            <el-form-item label="在即時監控顯示測試辨識工具">
              <el-switch v-model="testToolsEnabled" />
              <span class="text-muted text-sm" style="margin-left: 12px">只套用在這台電腦的瀏覽器</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>

      <!-- 帳號管理 -->
      <el-tab-pane label="操作員帳號" name="users">
        <el-card shadow="never">
          <div style="display: flex; justify-content: flex-end; margin-bottom: 12px">
            <el-button type="primary" @click="userDlg = true">新增操作員</el-button>
          </div>
          <el-table :data="users" stripe>
            <el-table-column prop="username" label="帳號" width="150" />
            <el-table-column prop="display_name" label="顯示名稱" width="150" />
            <el-table-column label="狀態" width="100">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                  {{ row.is_active ? '啟用' : '停用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="建立時間" width="180">
              <template #default="{ row }">{{ fmtDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="200">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="toggleUser(row)">
                  {{ row.is_active ? '停用' : '啟用' }}
                </el-button>
                <el-button link type="warning" size="small" @click="resetUserPw(row)">重設密碼</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-tab-pane>
    </el-tabs>

    <!-- 車道設定對話框 -->
    <el-dialog v-model="laneDlg" :title="laneForm.id ? '編輯車道' : '新增車道'" width="560px">
      <el-form label-width="115px">
        <el-form-item label="車道名稱" required>
          <el-input v-model="laneForm.name" placeholder="例：大門入口 / 機車出口" />
        </el-form-item>
        <el-form-item label="方向">
          <el-radio-group v-model="laneForm.direction">
            <el-radio value="IN">進場</el-radio>
            <el-radio value="OUT">離場</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="車道車種">
          <el-radio-group v-model="laneForm.vehicle_types">
            <el-radio value="BOTH">汽機車皆可</el-radio>
            <el-radio value="CAR">汽車專用</el-radio>
            <el-radio value="MOTO">機車專用</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="攝影機來源">
          <el-input
            v-model="laneForm.source_url"
            placeholder="http://手機IP:8080/video 或 rtsp://... 或 0 或影片檔路徑"
          />
        </el-form-item>
        <el-form-item v-if="laneForm.id" label="手機當攝影機">
          <el-button size="small" type="warning" plain @click="showQr(laneForm as any)">
            📱 掃描 QR Code 連線手機鏡頭
          </el-button>
        </el-form-item>
        <el-form-item label="柵欄驅動">
          <el-select v-model="laneForm.gate_driver" style="width: 100%">
            <el-option v-for="d in drivers" :key="d.value" :label="d.label" :value="d.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="laneForm.gate_driver !== 'simulated'" label="驅動參數 (JSON)">
          <el-input
            v-model="laneForm.gate_config_json"
            type="textarea"
            :rows="3"
            :placeholder="laneForm.gate_driver === 'http_relay' ? '{&quot;url&quot;: &quot;http://192.168.1.50/relay/0?turn=on&amp;timer=2&quot;}' : '{&quot;host&quot;: &quot;192.168.1.60&quot;, &quot;port&quot;: 502, &quot;coil&quot;: 0}'"
          />
        </el-form-item>
        <el-form-item label="未知車自動放行">
          <el-switch v-model="laneForm.auto_allow_unknown" />
          <span class="text-muted text-xs" style="margin-left: 8px">（建議僅出口車道勾選）</span>
        </el-form-item>
        <el-form-item label="啟用車道">
          <el-switch v-model="laneForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="laneDlg = false">取消</el-button>
        <el-button type="primary" @click="saveLane">儲存</el-button>
      </template>
    </el-dialog>

    <!-- 新增帳號對話框 -->
    <el-dialog v-model="userDlg" title="新增操作員帳號" width="400px">
      <el-form label-width="85px">
        <el-form-item label="帳號" required>
          <el-input v-model="newUser.username" placeholder="英數字" />
        </el-form-item>
        <el-form-item label="顯示名稱">
          <el-input v-model="newUser.display_name" placeholder="例：早班警衛" />
        </el-form-item>
        <el-form-item label="密碼" required>
          <el-input v-model="newUser.password" type="password" show-password placeholder="至少 6 碼" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDlg = false">取消</el-button>
        <el-button type="primary" @click="createUser">建立</el-button>
      </template>
    </el-dialog>

    <MobileCameraQrDialog v-model="qrDlg" :lane="qrLane" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MobileCameraQrDialog from '../components/MobileCameraQrDialog.vue'
import { useTestTools } from '../composables/useTestTools'
import {
  api,
  DIRECTION_LABEL,
  fmtDateTime,
  VEHICLE_TYPE_LABEL,
  type Lane,
  type SettingMeta,
  type SettingsResponse,
  type User,
} from '../api'

const tab = ref('lanes')
const { testToolsEnabled } = useTestTools()
const lanes = ref<Lane[]>([])
const drivers = ref<Array<{ value: string; label: string }>>([])
const settingMeta = ref<SettingMeta[]>([])
const settingValues = reactive<Record<string, any>>({})
const savingSettings = ref(false)
const users = ref<User[]>([])

const qrDlg = ref(false)
const qrLane = ref<Lane | null>(null)

function showQr(row: any) {
  qrLane.value = row
  qrDlg.value = true
}

const laneDlg = ref(false)
const laneForm = reactive({
  id: 0,
  name: '',
  direction: 'IN' as 'IN' | 'OUT',
  vehicle_types: 'BOTH' as 'CAR' | 'MOTO' | 'BOTH',
  source_url: '',
  gate_driver: 'simulated' as 'simulated' | 'http_relay' | 'modbus',
  gate_config_json: '{}',
  auto_allow_unknown: false,
  enabled: true,
})

const userDlg = ref(false)
const newUser = reactive({ username: '', display_name: '', password: '' })

function driverLabel(v: string) {
  return drivers.value.find((d) => d.value === v)?.label || v
}

async function loadAll() {
  const [l, meta, st, u] = await Promise.all([
    api.get<Lane[]>('/api/lanes'),
    api.get<{ drivers: Array<{ value: string; label: string }> }>('/api/lanes/meta'),
    api.get<SettingsResponse>('/api/settings'),
    api.get<User[]>('/api/users'),
  ])
  lanes.value = l
  drivers.value = meta.drivers
  settingMeta.value = st.meta
  Object.assign(settingValues, st.values)
  users.value = u
}

function openLane(l?: Lane) {
  laneForm.id = l?.id ?? 0
  laneForm.name = l?.name ?? ''
  laneForm.direction = l?.direction ?? 'IN'
  laneForm.vehicle_types = l?.vehicle_types ?? 'BOTH'
  laneForm.source_url = l?.source_url ?? ''
  laneForm.gate_driver = l?.gate_driver ?? 'simulated'
  laneForm.gate_config_json = JSON.stringify(l?.gate_config ?? {}, null, 2)
  laneForm.auto_allow_unknown = l?.auto_allow_unknown ?? false
  laneForm.enabled = l?.enabled ?? true
  laneDlg.value = true
}

async function saveLane() {
  let gate_config: Record<string, unknown> = {}
  if (laneForm.gate_driver !== 'simulated' && laneForm.gate_config_json.trim()) {
    try {
      gate_config = JSON.parse(laneForm.gate_config_json)
    } catch {
      ElMessage.error('驅動參數必須為合法 JSON')
      return
    }
  }
  const payload = {
    name: laneForm.name,
    direction: laneForm.direction,
    vehicle_types: laneForm.vehicle_types,
    source_url: laneForm.source_url.trim(),
    gate_driver: laneForm.gate_driver,
    gate_config,
    auto_allow_unknown: laneForm.auto_allow_unknown,
    enabled: laneForm.enabled,
  }
  try {
    if (laneForm.id) await api.put(`/api/lanes/${laneForm.id}`, payload)
    else await api.post('/api/lanes', payload)
    laneDlg.value = false
    ElMessage.success('車道設定已儲存')
    await loadAll()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function delLane(l: Lane) {
  await ElMessageBox.confirm(`確定刪除車道 ${l.name}？`, '確認', { type: 'warning' })
  await api.del(`/api/lanes/${l.id}`)
  ElMessage.success('已刪除')
  await loadAll()
}

async function testGate(l: Lane) {
  const res = await api.post<{ ok: boolean; message: string }>(`/api/lanes/${l.id}/test-gate`)
  if (res.ok) ElMessage.success(`測試成功：${res.message}`)
  else ElMessage.error(`測試失敗：${res.message}`)
}

async function saveSettings() {
  savingSettings.value = true
  try {
    const res = await api.put<SettingsResponse>('/api/settings', settingValues)
    Object.assign(settingValues, res.values)
    ElMessage.success('系統參數已儲存並生效')
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    savingSettings.value = false
  }
}

async function createUser() {
  try {
    await api.post('/api/users', newUser)
    userDlg.value = false
    newUser.username = ''
    newUser.display_name = ''
    newUser.password = ''
    ElMessage.success('已建立帳號')
    await loadAll()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function toggleUser(u: User) {
  try {
    await api.put(`/api/users/${u.id}`, { is_active: !u.is_active })
    await loadAll()
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function resetUserPw(u: User) {
  const { value } = await ElMessageBox.prompt(`請輸入 ${u.username} 的新密碼（至少 6 碼）`, '重設密碼', {
    inputType: 'password',
  })
  try {
    await api.put(`/api/users/${u.id}`, { password: value })
    ElMessage.success('密碼已重設')
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

onMounted(() => void loadAll())
</script>
