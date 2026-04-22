<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <el-container class="layout">
    <el-header class="header">
      <span class="brand">支撑孪生体新范式多维数据融合分析框架原型系统</span>
    </el-header>
    <el-container>
      <el-aside width="220px" class="aside">
        <el-menu :default-active="$route.path" router>
          <el-menu-item index="/">
            <el-icon><HomeFilled /></el-icon>
            <span>概览</span>
          </el-menu-item>
          <el-menu-item index="/domains">
            <el-icon><Grid /></el-icon>
            <span>业务域</span>
          </el-menu-item>
        </el-menu>
      </el-aside>
      <el-main><RouterView /></el-main>
    </el-container>
  </el-container>
</template>

<script lang="ts">
import { HomeFilled, Grid } from '@element-plus/icons-vue'
export default { components: { HomeFilled, Grid } }
</script>

<style scoped>
.layout { height: 100vh; }
.header {
  background: #0a2e5c;
  color: #fff;
  display: flex;
  align-items: center;
  font-size: 16px;
  font-weight: 600;
}
.aside { border-right: 1px solid #e6e8eb; }
</style>
