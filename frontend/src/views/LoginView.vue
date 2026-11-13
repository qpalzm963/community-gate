<template>
  <div class="login-page">
    <div class="backdrop" aria-hidden="true">
      <div class="glow glow-a" />
      <div class="glow glow-b" />
      <svg class="skyline" viewBox="0 0 1200 260" preserveAspectRatio="xMidYMax slice">
        <path
          d="M0 260 V190 H60 V140 H110 V170 H150 V96 H210 V150 H250 V120 H300 V180 H350 V70 H420 V160 H470 V130 H520 V200 H580 V110 H640 V60 H700 V150 H760 V120 H800 V170 H860 V90 H930 V150 H980 V130 H1030 V190 H1090 V140 H1140 V180 H1200 V260 Z"
        />
      </svg>
    </div>

    <main class="login-wrap">
      <section class="brand-panel">
        <BrandCrest :name="appState.communityName" :size="64" />
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
            <el-input v-model="form.username" placeholder="請輸入帳號" autocomplete="username" autofocus :prefix-icon="UserIcon" />
          </el-form-item>
          <el-form-item label="密碼">
            <el-input
              v-model="form.password"
              type="password"
              show-password
              placeholder="請輸入密碼"
              autocomplete="current-password"
              :prefix-icon="Lock"
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
import { Lock, User as UserIcon } from '@element-plus/icons-vue'
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
.skyline {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  height: 34vh;
  fill: color-mix(in srgb, var(--cg-gold) 7%, transparent);
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
.brand-name {
  margin: 24px 0 10px;
  font-family: var(--cg-font-serif);
  font-size: var(--cg-text-3xl);
  font-weight: 600;
  letter-spacing: 0.1em;
  color: var(--cg-text-inverse);
}
.brand-tagline {
  margin: 0 0 28px;
  font-size: var(--cg-text-lg);
  letter-spacing: 0.16em;
  color: var(--cg-gold);
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
  padding: 36px 32px 32px;
  border-radius: var(--cg-radius-lg);
  background: color-mix(in srgb, var(--cg-surface) 97%, transparent);
  border: 1px solid color-mix(in srgb, var(--cg-gold) 30%, transparent);
  box-shadow: var(--cg-shadow-lg);
  backdrop-filter: blur(18px) saturate(140%);
  color: var(--cg-text);
}
.card-title {
  margin: 0;
  font-family: var(--cg-font-serif);
  font-size: var(--cg-text-xl);
  font-weight: 600;
  letter-spacing: 0.08em;
}
.card-sub {
  margin: 6px 0 24px;
  font-size: var(--cg-text-sm);
  color: var(--cg-text-3);
}
.submit-btn {
  width: 100%;
  margin-top: 8px;
  height: 46px;
  font-size: var(--cg-text-lg);
  letter-spacing: 0.3em;
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
