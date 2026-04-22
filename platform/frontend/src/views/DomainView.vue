<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listDomains, type DomainItem } from '@/api/system'

const domains = ref<DomainItem[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const r = await listDomains()
    if (r.code === 0 && r.data) domains.value = r.data
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <el-card v-loading="loading">
    <template #header>业务域 (共 {{ domains.length }} 个)</template>
    <el-table :data="domains" border stripe>
      <el-table-column prop="code" label="编码" width="160" />
      <el-table-column prop="name" label="名称" />
      <el-table-column label="业务架构" align="center" width="110">
        <template #default="{ row }">
          <el-tag :type="row.hasBusinessArchitecture ? 'success' : 'info'">
            {{ row.hasBusinessArchitecture ? '✓' : '—' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="数据架构" align="center" width="110">
        <template #default="{ row }">
          <el-tag :type="row.hasDataArchitecture ? 'success' : 'info'">
            {{ row.hasDataArchitecture ? '✓' : '—' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="应用架构" align="center" width="110">
        <template #default="{ row }">
          <el-tag :type="row.hasApplicationArchitecture ? 'success' : 'info'">
            {{ row.hasApplicationArchitecture ? '✓' : '—' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>
