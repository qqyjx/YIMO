<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { listDomains, type DomainItem } from '@/api/system'

const domains = ref<DomainItem[]>([])
const loading = ref(true)
const search = ref('')

onMounted(async () => {
  try {
    const r = await listDomains()
    if (r.code === 0 && r.data) domains.value = r.data
  } finally {
    loading.value = false
  }
})

const filtered = computed(() => {
  const q = search.value.trim()
  if (!q) return domains.value
  return domains.value.filter(d => d.code.includes(q) || d.name.includes(q))
})

const completeCount = computed(() =>
  domains.value.filter(d => d.hasBusinessArchitecture && d.hasDataArchitecture && d.hasApplicationArchitecture).length
)
</script>

<template>
  <div>
    <!-- 规范 6.1 表单录入 + 6.2 按钮摆放 (列表操作按钮放左上, 见规范 991 行) -->
    <el-card shadow="never" class="head-card">
      <div class="head-row">
        <div>
          <div class="head-title">业务域清单</div>
          <div class="csg-muted">共 {{ domains.length }} 个域，三层架构齐全 {{ completeCount }} 个</div>
        </div>
        <div class="head-actions csg-btn-group">
          <el-input
            v-model="search"
            placeholder="搜索域编码/名称 (Ctrl+K)"
            clearable
            style="width:280px;"
            :prefix-icon="'Search' as any"
          />
          <el-button type="primary" :icon="'Refresh' as any" @click="$router.go(0)">刷新</el-button>
        </div>
      </div>
    </el-card>

    <!-- 数据表格 (规范第 6 章: 行选中支持整行点击, 关键列居中) -->
    <el-card shadow="never" class="table-card" v-loading="loading">
      <el-table
        :data="filtered"
        stripe
        border
        :header-cell-style="{ background: '#f4f8fd', color: 'var(--csg-text-sub)', fontWeight: 600 }"
        size="default"
        row-key="code"
      >
        <el-table-column prop="code" label="域编码" width="180" />
        <el-table-column prop="name" label="域名称" />
        <el-table-column label="业务架构 BA" align="center" width="130">
          <template #default="{ row }">
            <el-tag v-if="row.hasBusinessArchitecture" type="success" effect="plain">✓ 已接入</el-tag>
            <el-tag v-else type="info" effect="plain">— 未接入</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="数据架构 DA" align="center" width="130">
          <template #default="{ row }">
            <el-tag v-if="row.hasDataArchitecture" type="success" effect="plain">✓ 已接入</el-tag>
            <el-tag v-else type="info" effect="plain">— 未接入</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="应用架构 AA" align="center" width="130">
          <template #default="{ row }">
            <el-tag v-if="row.hasApplicationArchitecture" type="success" effect="plain">✓ 已接入</el-tag>
            <el-tag v-else type="info" effect="plain">— 未接入</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="完整性" align="center" width="110">
          <template #default="{ row }">
            <el-tag
              v-if="row.hasBusinessArchitecture && row.hasDataArchitecture && row.hasApplicationArchitecture"
              type="success"
            >完整</el-tag>
            <el-tag v-else type="warning">部分</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.head-card {
  margin-bottom: var(--csg-gap-lg);
  border: 1px solid var(--csg-border-light);
  border-radius: var(--csg-radius);
}
.head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--csg-gap-md);
}
.head-title { font-weight: 600; font-size: 16px; color: var(--csg-text-main); margin-bottom: 4px; }
.head-actions { display: flex; align-items: center; gap: var(--csg-gap-btn); }

.table-card {
  border: 1px solid var(--csg-border-light);
  border-radius: var(--csg-radius);
}
:deep(.el-table) {
  font-size: var(--csg-font-size-base);
}
</style>
