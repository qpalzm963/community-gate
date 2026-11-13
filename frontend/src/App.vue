<template>
  <router-view v-if="isLoginRoute" />
  <el-container v-else class="app-shell">
    <el-aside width="220px" class="sidebar">
      <div class="brand">
        <el-icon :size="22"><Van /></el-icon>
        <span>{{ appState.communityName }}</span>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#0f172a"
        text-color="#cbd5e1"
        active-text-color="#ffffff"
        class="side-menu"
      >
        <el-menu-item index="/">
          <el-icon><VideoCamera /></el-icon>
          <span>即時監控</span>
          <el-badge v-if="appState.pendingEvents.length" :value="appState.pendingEvents.length" class="menu-badge" />
        </el-menu-item>
        <el-menu-item index="/households">
          <el-icon><House /></el-icon>
          <span>住戶與車輛</span>
        </el-menu-item>
        <el-menu-item index="/visitors">
          <el-icon><User /></el-icon>
          <span>訪客管理</span>
        </el-menu-item>
        <el-menu-item index="/blacklist">
          <el-icon><Warning /></el-icon>
          <span>黑名單</span>
        </el-menu-item>
        <el-menu-item index="/events">
          <el-icon><Document /></el-icon>
          <span>進出紀錄</span>
        </el-menu-item>
        <el-menu-item index="/alerts">
          <el-icon><Bell /></el-icon>
          <span>警示中心</span>
          <el-badge v-if="appState.unackAlerts" :value="appState.unackAlerts" class="menu-badge" />
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>系統設定</span>
        </el-menu-item>
      </el-menu>

      <div class="user-footer">
        <div class="user-name">{{ appState.user?.display_name || appState.user?.username }}</div>
        <div class="user-actions">
          <el-button link type="info" size="small" @click="pwDialog = true">改密碼</el-button>
          <el-button link type="danger" size="small" @click="logout">登出</el-button>
        </div>
      </div>
    </el-aside>

    <el-main class="main-area">
      <router-view />
    </el-main>

    <PendingDecisionDialog />

    <el-dialog v-model="pwDialog" title="修改密碼" width="400px">
      <el-form label-width="90px">
        <el-form-item label="舊密碼">
          <el-input v-model="pwForm.old_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密碼">
          <el-input v-model="pwForm.new_password" type="password" show-password placeholder="至少 6 碼" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwDialog = false">取消</el-button>
        <el-button type="primary" :loading="pwSaving" @click="savePassword">儲存</el-button>
      </template>
    </el-dialog>
  </el-container>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, setUnauthorizedHandler, type User } from './api'
import { appState, initWsListeners, loadPublicInfo, refreshPendingAndAlerts } from './store'
import { wsHub } from './ws'
import PendingDecisionDialog from './components/PendingDecisionDialog.vue'

const route = useRoute()
const router = useRouter()
const isLoginRoute = computed(() => route.path === '/login')

const pwDialog = ref(false)
const pwSaving = ref(false)
const pwForm = reactive({ old_password: '', new_password: '' })

setUnauthorizedHandler(() => {
  appState.user = null
  wsHub.disconnect()
  if (route.path !== '/login') {
    void router.push('/login')
  }
})

async function ensureSession() {
  await loadPublicInfo()
  try {
    appState.user = await api.get<User>('/api/auth/me')
    initWsListeners()
    wsHub.connect()
    await refreshPendingAndAlerts()
    if (route.path === '/login') {
      void router.replace('/')
    }
  } catch {
    appState.user = null
    if (route.path !== '/login') {
      void router.replace('/login')
    }
  }
}

watch(
  () => appState.user,
  (u) => {
    if (u) {
      initWsListeners()
      wsHub.connect()
      void refreshPendingAndAlerts()
    } else {
      wsHub.disconnect()
    }
  },
)

onMounted(() => {
  void ensureSession()
})

async function logout() {
  try {
    await api.post('/api/auth/logout')
  } finally {
    appState.user = null
    wsHub.disconnect()
    void router.push('/login')
  }
}

async function savePassword() {
  pwSaving.value = true
  try {
    await api.post('/api/auth/change-password', pwForm)
    ElMessage.success('密碼已更新')
    pwDialog.value = false
    pwForm.old_password = ''
    pwForm.new_password = ''
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    pwSaving.value = false
  }
}
</script>

<style scoped>
.app-shell {
  min-height: 100vh;
}
.sidebar {
  background: #0f172a;
  color: #f8fafc;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px;
  font-size: 16px;
  font-weight: 700;
  border-bottom: 1px solid #1e293b;
}
.side-menu {
  border-right: none;
  flex: 1;
}
.menu-badge {
  margin-left: auto;
}
.user-footer {
  padding: 14px 16px;
  border-top: 1px solid #1e293b;
}
.user-name {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 4px;
}
.user-actions {
  display: flex;
  gap: 12px;
}
.main-area {
  padding: 20px;
  overflow-x: hidden;
}
</style>
