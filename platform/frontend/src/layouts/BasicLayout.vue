<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <el-container class="layout">
    <!-- 规范第 7 章: 顶部品牌栏, 高度 56px -->
    <el-header class="header csg-page-header">
      <span class="brand-icon">孪</span>
      <span class="brand-title">支撑孪生体新范式多维数据融合分析框架原型系统</span>
      <span class="brand-tag">v0.1 · 合规版</span>
    </el-header>
    <el-container>
      <el-aside width="220px" class="aside">
        <el-menu :default-active="$route.path" router class="csg-menu">
          <el-menu-item index="/">
            <el-icon><HomeFilled /></el-icon>
            <span>概览</span>
          </el-menu-item>
          <el-menu-item index="/domains">
            <el-icon><Grid /></el-icon>
            <span>业务域</span>
          </el-menu-item>
        </el-menu>
        <div class="aside-foot csg-muted">
          <div>南方电网深圳数字电网研究院</div>
          <div>WebUI 规范 v3.1 (2021.9)</div>
        </div>
      </el-aside>
      <el-main class="main"><RouterView /></el-main>
    </el-container>
  </el-container>
</template>

<script lang="ts">
import { HomeFilled, Grid } from '@element-plus/icons-vue'
export default { components: { HomeFilled, Grid } }
</script>

<style scoped>
.layout { height: 100vh; }

/* 顶部栏: 渐变 + 56px 高 (csg-tokens.css 已定义 .csg-page-header) */
.header {
  height: 56px !important;
  line-height: 56px;
  padding: 0 var(--csg-gap-xl);
  display: flex;
  align-items: center;
  gap: var(--csg-gap-md);
}
.brand-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px; height: 28px;
  border-radius: var(--csg-radius);
  background: rgba(255,255,255,0.18);
  font-weight: 600;
}
.brand-title { font-weight: 600; font-size: 16px; }
.brand-tag {
  margin-left: auto;
  font-size: var(--csg-font-size-small);
  padding: 2px 8px;
  border: 1px solid rgba(255,255,255,0.4);
  border-radius: var(--csg-radius);
  opacity: 0.85;
}

/* 侧栏: 灰底白边, 与规范"对齐 + 一致性"原则 */
.aside {
  background: var(--csg-bg-card);
  border-right: 1px solid var(--csg-border-light);
  display: flex;
  flex-direction: column;
}
.csg-menu { border-right: 0; }
.aside-foot {
  margin-top: auto;
  padding: var(--csg-gap-md) var(--csg-gap-lg);
  border-top: 1px solid var(--csg-border-light);
  font-size: var(--csg-font-size-small);
  color: var(--csg-text-muted);
  line-height: 1.5;
}

.main {
  background: var(--csg-bg);
  padding: var(--csg-gap-lg);
}
</style>
