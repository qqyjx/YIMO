import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// 南网数字平台 Web 应用界面设计规范 token (CSG-SZDGRI-STD-WebUI v3.1)
// 必须在 element-plus/dist/index.css 之后引入, 才能覆盖 ElementPlus 默认变量
import './styles/csg-tokens.css'
import App from './App.vue'
import router from './router'

// Element Plus 作为临时 UI 库;上线前替换为南网数字平台组件库 SDK.
const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus)
app.mount('#app')
