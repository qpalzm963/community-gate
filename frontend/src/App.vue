<template>
  <router-view v-if="isStandaloneRoute" />
  <el-container v-else class="app-shell">
    <el-aside :width="narrow ? '76px' : '236px'" class="sidebar" :class="{ narrow }">
      <div class="brand">
        <BrandCrest :name="appState.communityName" :size="narrow ? 36 : 40" />
        <div v-if="!narrow" class="brand-text">
          <div class="brand-name">{{ appState.communityName }}</div>
          <div class="brand-sub">出入管理中控台</div>
        </div>
      </div>

      <el-menu :default-active="route.path" router :collapse="narrow" class="side-menu">
        <el-menu-item v-for="item in menu" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>
            <span>{{ item.label }}</span>
            <span v-if="item.badge()" class="menu-badge" :class="item.badgeTone">{{ item.badge() }}</span>
          </template>
        </el-menu-item>
      </el-menu>

      <div class="user-footer">
        <div class="avatar" :title="userName">{{ userInitial }}</div>
        <div v-if="!narrow" class="user-meta">
          <div class="user-name">{{ userName }}</div>
          <div class="user-duty"><span class="duty-dot" />值班中 · {{ appState.user?.username }}</div>
        </div>
        <el-dropdown trigger="click" placement="top-end" @command="onUserCommand">
          <el-button text circle class="user-more" aria-label="帳號選單">
            <el-icon><MoreFilled /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="password" :icon="Lock">修改密碼</el-dropdown-item>
              <el-dropdown-item command="logout" :icon="SwitchButton" divided>登出</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-aside>

    <el-container direction="vertical" class="main-col">
      <header class="topbar">
        <div class="clock">
          <span class="clock-time mono">{{ clockTime }}</span>
          <span class="clock-date">{{ clockDate }}</span>
        </div>
        <div class="topbar-right">
          <span v-if="appState.pendingEvents.length" class="status-chip warn" role="status">
            <el-icon><BellFilled /></el-icon>待處理 {{ appState.pendingEvents.length }}
          </span>
          <span class="status-chip" :class="wsState.connected ? 'ok' : 'err'" role="status">
            <span class="status-dot" />{{ wsState.connected ? '即時連線正常' : '連線中斷，重新連線中' }}
          </span>
          <el-tooltip :content="`外觀：${themeLabel}（點擊切換）`" placement="bottom">
            <el-button circle class="theme-btn" :aria-label="`切換外觀，目前為${themeLabel}`" @click="cycleTheme">
              <el-icon>
                <Moon v-if="themePref === 'dark'" />
                <Sunny v-else-if="themePref === 'light'" />
                <Monitor v-else />
              </el-icon>
            </el-button>
          </el-tooltip>
        </div>
      </header>

      <el-main class="main-area">
        <router-view v-slot="{ Component }">
          <transition name="fade-rise" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>

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
import { computed, onMounted, onUnmounted, reactive, ref, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Bell,
  BellFilled,
  Document,
  House,
  Lock,
  Monitor,
  Moon,
  MoreFilled,
  Setting,
  Sunny,
  SwitchButton,
  User as UserIcon,
  VideoCamera,
  Warning,
} from '@element-plus/icons-vue'
import { api, setUnauthorizedHandler, type User } from './api'
import { appState, initWsListeners, loadPublicInfo, refreshPendingAndAlerts } from './store'
import { wsHub, wsState } from './ws'
import { useTheme } from './composables/useTheme'
import BrandCrest from './components/BrandCrest.vue'
import PendingDecisionDialog from './components/PendingDecisionDialog.vue'

interface MenuItem {
  path: string
  label: string
  icon: Component
  badge: () => number
  badgeTone?: string
}

const menu: MenuItem[] = [
  { path: '/', label: '即時監控', icon: VideoCamera, badge: () => appState.pendingEvents.length, badgeTone: 'warn' },
  { path: '/households', label: '住戶與車輛', icon: House, badge: () => 0 },
  { path: '/visitors', label: '訪客管理', icon: UserIcon, badge: () => 0 },
  { path: '/blacklist', label: '黑名單', icon: Warning, badge: () => 0 },
  { path: '/events', label: '進出紀錄', icon: Document, badge: () => 0 },
  { path: '/alerts', label: '警示中心', icon: Bell, badge: () => appState.unackAlerts, badgeTone: 'danger' },
  { path: '/settings', label: '系統設定', icon: Setting, badge: () => 0 },
]

const { preference: themePref, label: themeLabel, cycle: cycleTheme } = useTheme()

const userName = computed(() => appState.user?.display_name || appState.user?.username || '')
const userInitial = computed(() => Array.from(userName.value.trim())[0] ?? '?')

// 值班螢幕常駐的時鐘
const now = ref(new Date())
const clockTime = computed(() => now.value.toLocaleTimeString('zh-TW', { hour12: false }))
const clockDate = computed(() =>
  now.value.toLocaleDateString('zh-TW', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' }),
)
let clockTimer: number | null = null

// 平板寬度（< 1024px）側邊欄收合為圖示列
const narrowQuery = window.matchMedia('(max-width: 1023px)')
const narrow = ref(narrowQuery.matches)
const onNarrowChange = (e: MediaQueryListEvent) => {
  narrow.value = e.matches
}

function onUserCommand(cmd: string) {
  if (cmd === 'password') pwDialog.value = true
  else if (cmd === 'logout') void logout()
}

const route = useRoute()
const router = useRouter()
const isStandaloneRoute = computed(() => Boolean(route.meta.standalone || route.path === '/login' || route.path === '/mobile-cam'))

const pwDialog = ref(false)
const pwSaving = ref(false)
const pwForm = reactive({ old_password: '', new_password: '' })

setUnauthorizedHandler(() => {
  appState.user = null
  wsHub.disconnect()
  if (!route.meta.public && route.path !== '/login' && route.path !== '/mobile-cam') {
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
    if (!route.meta.public && route.path !== '/login' && route.path !== '/mobile-cam') {
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
  clockTimer = window.setInterval(() => {
    now.value = new Date()
  }, 1000)
  narrowQuery.addEventListener('change', onNarrowChange)
})

onUnmounted(() => {
  if (clockTimer !== null) clearInterval(clockTimer)
  narrowQuery.removeEventListener('change', onNarrowChange)
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

/* ---- 側邊欄 ---- */
.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  background: linear-gradient(180deg, var(--cg-side-bg) 0%, var(--cg-side-bg-2) 100%);
  color: var(--cg-side-text);
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--cg-side-border);
  transition: width var(--cg-duration) var(--cg-ease);
  overflow: hidden;
}
.brand {
  display: flex;
  align-items: center;
  gap: var(--cg-space-3);
  padding: 22px 18px 20px;
  border-bottom: 1px solid var(--cg-side-border);
}
.sidebar.narrow .brand {
  justify-content: center;
  padding: 20px 0;
}
.brand-text {
  min-width: 0;
}
.brand-name {
  font-family: var(--cg-font-serif);
  font-size: var(--cg-text-lg);
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--cg-text-inverse);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.brand-sub {
  margin-top: 2px;
  font-size: var(--cg-text-xs);
  letter-spacing: 0.18em;
  color: var(--cg-gold);
}

.side-menu {
  --el-menu-bg-color: transparent;
  --el-menu-hover-bg-color: var(--cg-side-active-bg);
  --el-menu-text-color: var(--cg-side-text);
  --el-menu-active-color: var(--cg-text-inverse);
  --el-menu-item-height: 48px;
  border-right: none;
  flex: 1;
  padding: var(--cg-space-3) 0;
  overflow-y: auto;
}
.side-menu :deep(.el-menu-item) {
  position: relative;
  margin: 2px 10px;
  border-radius: var(--cg-radius-md);
  letter-spacing: 0.06em;
}
.side-menu.el-menu--collapse :deep(.el-menu-item) {
  margin: 2px 12px;
}
.side-menu :deep(.el-menu-item.is-active) {
  background: var(--cg-side-active-bg);
}
/* 金色選取指示條 */
.side-menu :deep(.el-menu-item.is-active)::before {
  content: "";
  position: absolute;
  left: -10px;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--cg-gold);
}
.side-menu :deep(.el-menu-item.is-active .el-icon) {
  color: var(--cg-gold);
}
.menu-badge {
  margin-left: auto;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: var(--cg-radius-pill);
  font-size: var(--cg-text-xs);
  line-height: 20px;
  text-align: center;
  font-weight: 600;
  color: var(--cg-text-inverse);
  background: var(--cg-danger);
}
.menu-badge.warn {
  background: var(--cg-warning);
}

.user-footer {
  display: flex;
  align-items: center;
  gap: var(--cg-space-3);
  padding: 14px 14px 16px 18px;
  border-top: 1px solid var(--cg-side-border);
}
.sidebar.narrow .user-footer {
  flex-direction: column;
  padding: 14px 0;
  gap: var(--cg-space-2);
}
.avatar {
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-family: var(--cg-font-serif);
  font-weight: 600;
  font-size: var(--cg-text-lg);
  color: var(--cg-navy-deep);
  background: linear-gradient(135deg, var(--cg-gold-soft), var(--cg-gold));
  box-shadow: 0 0 0 2px var(--cg-side-bg), 0 0 0 3px color-mix(in srgb, var(--cg-gold) 60%, transparent);
}
.user-meta {
  flex: 1;
  min-width: 0;
}
.user-name {
  font-size: var(--cg-text-md);
  font-weight: 600;
  color: var(--cg-text-inverse);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.user-duty {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
  font-size: var(--cg-text-xs);
  color: var(--cg-side-text-dim);
}
.duty-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--cg-success-text);
}
.user-more {
  --el-button-text-color: var(--cg-side-text);
  --el-button-hover-text-color: var(--cg-text-inverse);
  --el-button-hover-bg-color: var(--cg-side-active-bg);
}

/* ---- 頁首 ---- */
.main-col {
  min-width: 0;
}
.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--cg-space-4);
  padding: 12px 28px;
  background: color-mix(in srgb, var(--cg-bg) 86%, transparent);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--cg-border);
}
.clock {
  display: flex;
  align-items: baseline;
  gap: var(--cg-space-3);
}
.clock-time {
  font-size: var(--cg-text-xl);
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--cg-text);
}
.clock-date {
  font-size: var(--cg-text-sm);
  color: var(--cg-text-3);
  letter-spacing: 0.04em;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: var(--cg-space-2);
}
.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  border-radius: var(--cg-radius-pill);
  border: 1px solid var(--cg-border);
  background: var(--cg-surface);
  font-size: var(--cg-text-sm);
  color: var(--cg-text-2);
  white-space: nowrap;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}
.status-chip.ok {
  color: var(--cg-success-text);
}
.status-chip.err {
  color: var(--cg-danger-text);
  border-color: color-mix(in srgb, var(--cg-danger) 40%, var(--cg-border));
}
.status-chip.warn {
  color: var(--cg-warning-text);
  border-color: color-mix(in srgb, var(--cg-warning) 40%, var(--cg-border));
  background: color-mix(in srgb, var(--cg-warning) 8%, var(--cg-surface));
}
.status-chip.ok .status-dot {
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--cg-success) 22%, transparent);
}
.theme-btn {
  --el-button-bg-color: var(--cg-surface);
  --el-button-border-color: var(--cg-border);
  --el-button-text-color: var(--cg-text-2);
  --el-button-hover-text-color: var(--cg-gold-text);
  --el-button-hover-border-color: var(--cg-gold);
  --el-button-hover-bg-color: var(--cg-surface);
}

.main-area {
  padding: 28px;
  overflow-x: hidden;
}

@media (max-width: 1023px) {
  .topbar {
    padding: 10px 16px;
  }
  .clock-date {
    display: none;
  }
  .main-area {
    padding: 18px 16px;
  }
}
</style>
