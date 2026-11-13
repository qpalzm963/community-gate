import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import zhTw from 'element-plus/es/locale/lang/zh-tw'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
// 中文襯線字自帶：警衛室多為 Windows，沒裝 Noto Serif TC 會退回新細明體。
// 依 unicode-range 分塊，瀏覽器只下載畫面用到的字；不連外網，內網部署可用。
import '@fontsource/noto-serif-tc/400.css'
import '@fontsource/noto-serif-tc/500.css'
import '@fontsource/noto-serif-tc/600.css'
import './style.css'
import App from './App.vue'
import { router } from './router'
import { initTheme } from './composables/useTheme'

initTheme()

const app = createApp(App)
app.use(ElementPlus, { locale: zhTw })
app.use(router)
app.mount('#app')
