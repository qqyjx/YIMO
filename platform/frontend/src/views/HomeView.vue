<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getHealth, type HealthInfo } from '@/api/system'

const health = ref<HealthInfo | null>(null)
const loadErr = ref('')

onMounted(async () => {
  try {
    const r = await getHealth()
    if (r.code === 0 && r.data) health.value = r.data
    else loadErr.value = r.message
  } catch (e: unknown) {
    loadErr.value = (e as Error).message
  }
})
</script>

<template>
  <el-card>
    <template #header>系统健康</template>
    <el-descriptions v-if="health" :column="1" border>
      <el-descriptions-item label="系统名称">{{ health.systemName }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag type="success">{{ health.status }}</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="服务器时间">{{ health.time }}</el-descriptions-item>
    </el-descriptions>
    <el-alert v-else-if="loadErr" :title="loadErr" type="error" show-icon />
    <el-skeleton v-else animated :rows="3" />
  </el-card>
</template>
