<template>
  <div class="login-page">
    <el-card class="login-card">
      <div class="login-title">{{ appState.communityName }}</div>
      <div class="login-sub">社區日常出入管理（單機版）</div>
      <el-form @submit.prevent="submit" label-position="top">
        <el-form-item label="帳號">
          <el-input v-model="form.username" placeholder="請輸入帳號" autofocus />
        </el-form-item>
        <el-form-item label="密碼">
          <el-input v-model="form.password" type="password" show-password placeholder="請輸入密碼" />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading" style="width: 100%; margin-top: 8px">
          登入
        </el-button>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
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
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
}
.login-card {
  width: 380px;
  padding: 12px 8px;
}
.login-title {
  font-size: 22px;
  font-weight: 700;
  text-align: center;
  margin-bottom: 4px;
}
.login-sub {
  font-size: 13px;
  color: #64748b;
  text-align: center;
  margin-bottom: 20px;
}
</style>
