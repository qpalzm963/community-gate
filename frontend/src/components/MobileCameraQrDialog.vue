<template>
  <el-dialog
    v-model="visible"
    :title="`📱 手機掃描當攝影機 — ${lane?.name || '車道'}`"
    width="520px"
    destroy-on-close
    @open="onOpen"
    @close="onClose"
  >
    <div v-loading="loading" class="qr-dialog-body">
      <!-- 頂部即時連線狀態 -->
      <div class="conn-status-bar" :class="isPhoneConnected ? 'online' : 'waiting'">
        <span class="status-dot"></span>
        <span class="status-text">
          {{ isPhoneConnected ? `手機已連線傳輸中 (${lane?.status?.capture_fps || 0} fps)` : '等待手機掃描連線中...' }}
        </span>
      </div>

      <!-- QR Code 圖片展示 -->
      <div class="qr-wrapper">
        <img v-if="qrCodeDataUrl" :src="qrCodeDataUrl" alt="Camera QR Code" class="qr-img" />
        <div v-else class="qr-placeholder">產生中...</div>
      </div>

      <!-- 網址與自訂主機位址 -->
      <div class="url-section">
        <el-input v-model="customUrl" size="small" readonly>
          <template #append>
            <el-button @click="copyUrl">
              {{ copied ? '已複製！' : '複製網址' }}
            </el-button>
          </template>
        </el-input>
      </div>

      <!-- 連線進階自訂 (切換 IP / 協定) -->
      <el-collapse v-model="activeCollapse" style="margin-top: 12px; border: none;">
        <el-collapse-item title="調整主機 IP 或協定 (HTTPS / HTTP)" name="custom">
          <el-form label-width="70px" size="small" style="margin-top: 6px;">
            <el-form-item label="協定">
              <el-radio-group v-model="selectedScheme" @change="rebuildUrl">
                <el-radio value="https">https:// (推薦手機相機)</el-radio>
                <el-radio value="http">http://</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="主機 IP">
              <el-input v-model="serverHost" placeholder="例：192.168.1.100" @input="rebuildUrl" />
            </el-form-item>
            <el-form-item label="連接埠">
              <el-input v-model="serverPort" placeholder="預設留空或 8000" @input="rebuildUrl" />
            </el-form-item>
          </el-form>
        </el-collapse-item>
      </el-collapse>

      <div v-if="isLinkLocalIp" class="tips-box" style="margin-top: 10px; background: #fffbe6; border-color: #ffe58f; color: #d46b08;">
        <strong>⚠️ 偵測到不可路由的內部 IP ({{ serverHost }})：</strong>
        <p style="margin: 4px 0 0; font-size: 13px;">
          此位址為電腦虛擬/USB 連結專用，手機通常無法連入。請展開上方「調整主機 IP」手動修改為電腦的 Wi-Fi 區網 IP。
        </p>
      </div>

      <!-- 說明提醒區塊 -->
      <div class="tips-box" :class="selectedScheme === 'https' ? 'tip-https' : 'tip-http'">
        <div v-if="selectedScheme === 'https'">
          <strong>🔒 HTTPS 安全連線說明：</strong>
          <p>
            現代手機瀏覽器規定**必須在 HTTPS 安全連線下**才允許網頁開啟攝影機。
            若手機掃描後出現<em>「非私人連線 / 不安全」</em>警告，請點選<strong>「進階」</strong>並選擇<strong>「繼續前往此網站」</strong>即可授權相機！
          </p>
        </div>
        <div v-else>
          <strong>⚠️ HTTP 連線提醒：</strong>
          <p>
            多數手機瀏覽器在一般 HTTP (非 localhost) 下會**封鎖相機權限**。
            建議以 <code>uv run gate serve --host 0.0.0.0 --ssl</code> 啟動伺服器，並使用上方 HTTPS 連結。
          </p>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">關閉</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import QRCode from 'qrcode'
import { ElMessage } from 'element-plus'
import { api } from '../api'

interface LaneItem {
  id: number
  name: string
  status?: {
    online?: boolean
    capture_fps?: number
    is_push?: boolean
    last_error?: string
  }
}

const props = defineProps<{
  modelValue: boolean
  lane: LaneItem | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const loading = ref(false)
const copied = ref(false)
const qrCodeDataUrl = ref('')
const activeCollapse = ref<string[]>([])

const token = ref('')
const serverHost = ref('')
const serverPort = ref('')
const selectedScheme = ref('http')
const customUrl = ref('')

const isPhoneConnected = computed(() => Boolean(props.lane?.status?.is_push))
const isLinkLocalIp = computed(() => Boolean(serverHost.value && (serverHost.value.startsWith('169.254.') || serverHost.value === '127.0.0.1')))

async function onOpen() {
  if (!props.lane) return
  loading.value = true
  copied.value = false

  try {
    const res = await api.get<{
      lane_id: number
      token: string
      lan_ip: string
      port: number
      scheme: string
      connect_url: string
    }>(`/api/lanes/${props.lane.id}/camera-token`)

    token.value = res.token
    
    // 若瀏覽器目前是透過區網 IP (非 localhost/127.0.0.1/169.254) 連線，優先使用該 IP
    const currentHost = window.location.hostname
    if (currentHost && currentHost !== 'localhost' && currentHost !== '127.0.0.1' && !currentHost.startsWith('169.254.')) {
      serverHost.value = currentHost
    } else {
      serverHost.value = res.lan_ip
    }

    serverPort.value = String(window.location.port || res.port || '')
    selectedScheme.value = window.location.protocol.replace(':', '') || res.scheme || 'http'

    await rebuildUrl()
  } catch (err: any) {
    ElMessage.error(err.message || '取得攝影機憑證失敗')
  } finally {
    loading.value = false
  }
}

async function rebuildUrl() {
  if (!props.lane || !token.value) return
  let host = (serverHost.value || window.location.hostname).trim()
  let port = (serverPort.value || '').trim()

  // 若使用者在主機欄位直接貼了含 port 的字串 (例：192.168.1.100:8000)
  if (host.includes(':')) {
    const parts = host.split(':')
    host = parts[0]
    if (parts[1]) port = parts[1]
  }

  const portStr = port && port !== '80' && port !== '443' ? `:${port}` : ''
  const url = `${selectedScheme.value}://${host}${portStr}/mobile-cam?lane=${props.lane.id}&token=${encodeURIComponent(token.value)}`
  customUrl.value = url

  try {
    qrCodeDataUrl.value = await QRCode.toDataURL(url, {
      width: 280,
      margin: 2,
      color: {
        dark: '#0f172a',
        light: '#ffffff',
      },
    })
  } catch {
    qrCodeDataUrl.value = ''
  }
}

async function copyUrl() {
  try {
    await navigator.clipboard.writeText(customUrl.value)
    copied.value = true
    ElMessage.success('已複製手機連線網址')
    setTimeout(() => {
      copied.value = false
    }, 2500)
  } catch {
    ElMessage.info('請手動選取並複製網址')
  }
}

function onClose() {
  qrCodeDataUrl.value = ''
}
</script>

<style scoped>
.qr-dialog-body {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.conn-status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 16px;
}

.conn-status-bar.waiting {
  background: #f1f5f9;
  color: #64748b;
}

.conn-status-bar.waiting .status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #94a3b8;
}

.conn-status-bar.online {
  background: #ecfdf5;
  color: #059669;
}

.conn-status-bar.online .status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #10b981;
  box-shadow: 0 0 6px #10b981;
}

.qr-wrapper {
  background: #ffffff;
  padding: 10px;
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
  border: 1px solid #e2e8f0;
  margin-bottom: 16px;
}

.qr-img {
  width: 220px;
  height: 220px;
  display: block;
}

.qr-placeholder {
  width: 220px;
  height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #94a3b8;
}

.url-section {
  width: 100%;
}

.tips-box {
  width: 100%;
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 12px;
  line-height: 1.6;
  margin-top: 14px;
}

.tips-box strong {
  display: block;
  margin-bottom: 4px;
}

.tips-box p {
  margin: 0;
}

.tip-https {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #1e40af;
}

.tip-http {
  background: #fffbeb;
  border: 1px solid #fde68a;
  color: #b45309;
}
</style>
