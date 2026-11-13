<template>
  <div class="login-page">
    <div class="backdrop" aria-hidden="true">
      <div class="glow glow-a" />
      <div class="glow glow-b" />
      <!-- 細線拱門：社區大門意象，取代方塊天際線剪影 -->
      <svg class="arch" viewBox="0 0 520 640" fill="none">
        <path d="M20 640 V260 A240 240 0 0 1 500 260 V640" />
        <path d="M60 640 V270 A200 200 0 0 1 460 270 V640" />
        <path d="M110 640 V290 A150 150 0 0 1 410 290 V640" class="inner" />
        <path d="M160 640 V300 M210 640 V250 M260 640 V232 M310 640 V250 M360 640 V300" class="bars" />
        <path d="M110 420 H410" class="bars" />
      </svg>
    </div>

    <main class="login-wrap">
      <section class="brand-panel">
        <BrandCrest :name="appState.communityName" :size="64" />
        <div class="brand-eyebrow">Residential Access Console</div>
        <h1 class="brand-name">{{ appState.communityName }}</h1>
        <p class="brand-tagline">安心歸家，從每一次進出開始</p>
        <ul class="brand-points">
          <li>車牌辨識自動放行</li>
          <li>訪客預約與即時通報</li>
          <li>全天候值班中控台</li>
        </ul>
      </section>

      <section class="login-card" aria-labelledby="login-heading">
        <h2 id="login-heading" class="card-title">值班人員登入</h2>
        <p class="card-sub">請使用管理處核發的帳號</p>
        <el-form label-position="top" size="large" @submit.prevent="submit">
          <el-form-item label="帳號">
            <el-input v-model="form.username" autocomplete="username" autofocus />
          </el-form-item>
          <el-form-item label="密碼">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              autocomplete="current-password"
            />
          </el-form-item>
          <el-button type="primary" native-type="submit" :loading="loading" class="submit-btn">登入</el-button>
        </el-form>
      </section>
    </main>

    <footer class="login-foot">{{ appState.communityName }} · 管理委員會</footer>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import BrandCrest from '../components/BrandCrest.vue'
import { api, type User } from '../api'
import { appState } from '../store'

const router = useRouter()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

async function submit() {
  if (!form.username.trim() || !form.password) {
    ElMessage.warning('請輸入帳號與密碼')
    return
  }
  loading.value = true
  try {
    appState.user = await api.post<User>('/api/auth/login', form)
    void router.replace('/')
  } catch (err) {
    ElMessage.error((err as Error).message)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* 登入頁固定使用深色品牌底，不隨主題切換 */
.login-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: radial-gradient(120% 90% at 20% 10%, var(--cg-side-bg-2) 0%, var(--cg-side-bg) 55%, var(--cg-media-bg) 100%);
  color: var(--cg-overlay-text);
}
.backdrop {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.35;
}
.glow-a {
  width: 520px;
  height: 520px;
  left: -120px;
  top: -140px;
  background: color-mix(in srgb, var(--cg-gold) 45%, transparent);
}
.glow-b {
  width: 640px;
  height: 640px;
  right: -200px;
  bottom: -260px;
  background: color-mix(in srgb, var(--cg-navy) 80%, transparent);
}
/* 拱門只放在品牌區後方（品牌欄中心 = 視窗中心 - 232px），不跨到登入卡 */
.arch {
  position: absolute;
  left: calc(50% - 542px);
  bottom: -40px;
  width: 620px;
  height: auto;
  stroke: var(--cg-gold);
  stroke-width: 1;
  opacity: 0.16;
}
.arch .inner {
  opacity: 0.7;
}
.arch .bars {
  opacity: 0.45;
}

.login-wrap {
  position: relative;
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 400px;
  align-items: center;
  gap: 64px;
  width: min(1040px, 100% - 48px);
  margin: 0 auto;
  padding: 48px 0;
}
.brand-eyebrow {
  margin-top: 28px;
  font-size: 11px;
  letter-spacing: 0.32em;
  text-transform: uppercase;
  color: var(--cg-gold);
}
.brand-name {
  margin: 10px 0 12px;
  font-family: var(--cg-font-serif);
  font-size: 40px;
  font-weight: 500;
  letter-spacing: 0.12em;
  color: var(--cg-text-inverse);
}
.brand-tagline {
  margin: 0 0 28px;
  font-size: var(--cg-text-lg);
  font-weight: 300;
  letter-spacing: 0.2em;
  color: var(--cg-side-text);
}
.brand-points {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 12px;
  color: var(--cg-side-text);
  letter-spacing: 0.06em;
}
.brand-points li {
  display: flex;
  align-items: center;
  gap: 12px;
}
.brand-points li::before {
  content: "";
  width: 18px;
  height: 1px;
  background: var(--cg-gold);
}

/* 玻璃質感登入卡片 */
.login-card {
  padding: 44px 40px 40px;
  border-radius: 18px;
  background: color-mix(in srgb, var(--cg-surface) 97%, transparent);
  border: 1px solid var(--cg-hairline);
  box-shadow: var(--cg-shadow-lg);
  backdrop-filter: blur(18px) saturate(140%);
  color: var(--cg-text);
}
.card-title {
  margin: 0;
  font-family: var(--cg-font-serif);
  font-size: 22px;
  font-weight: 500;
  letter-spacing: 0.12em;
}
.card-sub {
  margin: 8px 0 28px;
  letter-spacing: 0.04em;
  font-size: var(--cg-text-sm);
  color: var(--cg-text-3);
}
.submit-btn {
  width: 100%;
  margin-top: 8px;
  height: 48px;
  font-size: var(--cg-text-md);
  letter-spacing: 0.4em;
}

.login-foot {
  position: relative;
  padding: 18px;
  text-align: center;
  font-size: var(--cg-text-xs);
  letter-spacing: 0.16em;
  color: var(--cg-side-text-dim);
}

@media (max-width: 860px) {
  .arch {
    left: 50%;
    width: min(620px, 92vw);
    transform: translateX(-50%);
  }
  .login-wrap {
    grid-template-columns: minmax(0, 420px);
    justify-content: center;
    gap: 32px;
  }
  .brand-panel {
    text-align: center;
  }
  .brand-panel :deep(.crest) {
    margin: 0 auto;
  }
  .brand-points {
    display: none;
  }
}
</style>
