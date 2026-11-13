<template>
  <el-card shadow="never">
    <template #header>
      <div class="lane-head">
        <div>
          <strong>{{ lane.name }}</strong>
          <el-tag size="small" style="margin-left: 8px">{{ DIRECTION_LABEL[lane.direction] }}</el-tag>
          <el-tag size="small" type="info" style="margin-left: 4px">
            {{ VEHICLE_TYPE_LABEL[lane.vehicle_types] }}
          </el-tag>
        </div>
        <div style="display: flex; align-items: center; gap: 8px">
          <el-tag :type="lane.status?.online ? 'success' : 'info'" size="small">
            {{ lane.status?.online ? `連線中 ${lane.status.capture_fps ?? ''}fps` : '離線 / 未接攝影機' }}
          </el-tag>
          <el-button size="small" @click="emit('show-qr', lane)">📱 手機鏡頭</el-button>
          <el-button type="primary" size="small" @click="manualOpenGate">手動開閘</el-button>
        </div>
      </div>
    </template>

    <div class="stream-wrap">
      <img :src="`/api/lanes/${lane.id}/stream`" class="stream-img" :alt="lane.name" />
      <div v-if="banner" class="gate-banner" :class="banner.ok ? 'ok' : 'err'">
        {{ banner.text }}
      </div>
    </div>

    <div class="lane-tools">
      <el-input
        v-model="simPlate"
        size="small"
        placeholder="輸入車牌模擬辨識 (例 ABC-1234)"
        style="width: 210px"
        @keyup.enter="simulatePlate"
      />
      <el-button size="small" @click="simulatePlate">模擬辨識</el-button>
      <el-upload
        :show-file-list="false"
        accept="image/*"
        :http-request="(opt: UploadRequestOptions) => uploadRecognize(opt.file)"
      >
        <el-button size="small" plain>上傳圖片辨識</el-button>
      </el-upload>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, type UploadRequestOptions } from 'element-plus'
import { api, DECISION_LABEL, DIRECTION_LABEL, VEHICLE_TYPE_LABEL, type AccessEvent, type Lane } from '../api'
import { appState } from '../store'

const props = defineProps<{ lane: Lane; nowTick: number }>()
const emit = defineEmits<{
  (e: 'show-qr', lane: Lane): void
  /** 車道上有動作（開閘、模擬、上傳辨識）後，請父層重新載入資料 */
  (e: 'changed'): void
}>()

const simPlate = ref('')

const banner = computed(() => {
  const g = appState.gateAnim[props.lane.id]
  if (!g || g.until < props.nowTick) return null
  return g
})

async function manualOpenGate() {
  try {
    await api.post(`/api/lanes/${props.lane.id}/open`, { note: '即時監控手動開閘' })
    ElMessage.success(`${props.lane.name} 已開閘`)
    emit('changed')
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

async function simulatePlate() {
  const plate = simPlate.value.trim()
  if (!plate) return
  try {
    await api.post(`/api/lanes/${props.lane.id}/simulate`, { plate })
    simPlate.value = ''
    emit('changed')
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}

interface RecognizeResult {
  detections: Array<{ plate_display: string | null; raw_text: string; confidence: number }>
  event: AccessEvent | null
}

async function uploadRecognize(file: File) {
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await api.upload<RecognizeResult>(`/api/lanes/${props.lane.id}/recognize?apply=true`, form)
    if (res.event) {
      ElMessage.success(`辨識結果：${res.event.plate_display}（${DECISION_LABEL[res.event.decision]}）`)
    } else if (res.detections.length > 0) {
      ElMessage.warning(`僅偵測到：${res.detections.map((d) => d.raw_text).join(', ')}（未符合車牌格式）`)
    } else {
      ElMessage.info('圖片中未偵測到車牌')
    }
    emit('changed')
  } catch (err) {
    ElMessage.error((err as Error).message)
  }
}
</script>

<style scoped>
.lane-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.stream-wrap {
  position: relative;
  background: #111827;
  border-radius: 6px;
  overflow: hidden;
  aspect-ratio: 16 / 9;
}
.stream-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}
.gate-banner {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  padding: 6px 16px;
  border-radius: 999px;
  font-weight: 600;
  color: #fff;
  font-size: 14px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35);
}
.gate-banner.ok { background: #16a34a; }
.gate-banner.err { background: #dc2626; }
.lane-tools {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
  flex-wrap: wrap;
}
</style>
