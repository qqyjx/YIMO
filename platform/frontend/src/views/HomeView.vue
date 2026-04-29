<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getHealth, type HealthInfo } from '@/api/system'
import http from '@/api/http'

const health = ref<HealthInfo | null>(null)
const loadErr = ref('')
const summary = ref<any>(null)

onMounted(async () => {
  try {
    const r = await getHealth()
    if (r.code === 0 && r.data) health.value = r.data
    else loadErr.value = r.message
  } catch (e: unknown) {
    loadErr.value = (e as Error).message
  }
  try {
    const s = await http.get<any>('/summary')
    summary.value = (s.data as any)?.data || null
  } catch { /* ignore */ }
})

function safe(v: unknown, suffix = '') {
  if (v === undefined || v === null) return '-'
  return suffix ? `${v}${suffix}` : String(v)
}
</script>

<template>
  <div class="home">
    <!-- 关键指标卡 (规范第 4 章对比原则 + 第 6 章按钮排列) -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-label csg-muted">业务域</div>
          <div class="stat-num">{{ safe(summary?.totalDomains) }}</div>
          <div class="csg-note">已抽取 {{ safe(summary?.extractedDomains) }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-label csg-muted">抽取对象</div>
          <div class="stat-num">{{ safe(summary?.totalObjects) }}</div>
          <div class="csg-note">含项目/合同/资产 等抽象对象</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card" shadow="never">
          <div class="stat-label csg-muted">三层关联</div>
          <div class="stat-num">{{ safe(summary?.totalRelations) }}</div>
          <div class="csg-note">概念 / 逻辑 / 物理</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="stat-card primary-card" shadow="never">
          <div class="stat-label">系统状态</div>
          <div class="stat-num" v-if="health">
            <el-tag size="large" type="success" effect="dark">{{ health.status }}</el-tag>
          </div>
          <el-skeleton v-else animated :rows="1"/>
          <div class="stat-time">{{ health?.time || '-' }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="info-card">
      <template #header>
        <div class="card-head">
          <span class="card-title">系统名称</span>
          <span class="csg-muted">出处: 任务书 / xuqiu1.md 第 63 行</span>
        </div>
      </template>
      <el-descriptions :column="1" border size="default" v-if="health">
        <el-descriptions-item label="系统全称" label-class-name="desc-label">
          {{ health.systemName }}
        </el-descriptions-item>
        <el-descriptions-item label="服务器时间" label-class-name="desc-label">
          {{ health.time }}
        </el-descriptions-item>
        <el-descriptions-item label="UI 规范" label-class-name="desc-label">
          南方电网深圳数字电网研究院 — Web 应用界面设计规范 v3.1
          (主色 #2590FF · 微软雅黑 · 文档参见 docs/需求/web应用界面设计规范.pdf)
        </el-descriptions-item>
      </el-descriptions>
      <el-alert v-else-if="loadErr" :title="loadErr" type="error" show-icon class="mt-md" />
      <el-skeleton v-else animated :rows="3" />
    </el-card>
  </div>
</template>

<style scoped>
.home { display: flex; flex-direction: column; gap: var(--csg-gap-lg); }
.stat-row { margin: 0 !important; }
.stat-card {
  border: 1px solid var(--csg-border-light);
  border-radius: var(--csg-radius);
  background: var(--csg-bg-card);
  text-align: left;
}
.stat-label { font-size: var(--csg-font-size-small); margin-bottom: 4px; }
.stat-num {
  font-size: 28px;
  font-weight: 600;
  color: var(--csg-primary);
  line-height: 1.3;
}
.stat-time { font-size: var(--csg-font-size-small); color: var(--csg-text-muted); margin-top: 4px; }
.primary-card .stat-num { color: var(--csg-text-main); }

.info-card {
  border: 1px solid var(--csg-border-light);
  border-radius: var(--csg-radius);
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-title { font-weight: 600; color: var(--csg-text-main); }
.mt-md { margin-top: var(--csg-gap-md); }
:deep(.desc-label) {
  width: 140px;
  background: #fafbfc;
  color: var(--csg-text-sub);
}
</style>
