<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const activeField = ref('')

const fields = computed(() => store.snapshot?.viewer.fields ?? [])
const resultFiles = computed(() => store.snapshot?.files.results ?? [])
const metrics = computed(() => store.snapshot?.viewer.metrics ?? [])

const slices = computed(() => [
  { label: '当前输入', value: store.snapshot?.active_input ?? '未发现' },
  { label: '结果文件', value: `${store.snapshot?.assets.result_files ?? 0} 个` },
  { label: '日志证据', value: `${store.snapshot?.assets.log_files ?? 0} 个` },
])

const activeMeta = computed(() => fields.value.find((field) => field.key === activeField.value) ?? fields.value[0])

function syncActiveField() {
  if (!activeField.value && fields.value.length) {
    activeField.value = fields.value[0].key
  }
}

onMounted(async () => {
  if (!store.snapshot) {
    await store.loadSnapshot()
  }
  syncActiveField()
})

watch(fields, syncActiveField)
</script>

<template>
  <div class="postprocess-workbench">
    <article class="panel result-viewport">
      <div class="viewport-toolbar">
        <div>
          <span class="section-label">后处理视窗</span>
          <h2>{{ store.snapshot?.viewer.has_results ? '真实结果文件' : '暂无结果文件' }}</h2>
        </div>
        <div class="chip-row">
          <button
            v-for="field in fields"
            :key="field.key"
            :class="activeField === field.key ? 'md-chip-active' : 'md-chip'"
            @click="activeField = field.key"
          >
            {{ field.label }}
          </button>
        </div>
      </div>

      <div class="technical-viewport">
        <div class="viewport-grid" />
        <div v-if="resultFiles.length" class="result-file-preview">
          <Icon icon="carbon:document" />
          <strong>{{ activeMeta?.max ?? resultFiles[0].name }}</strong>
          <span>{{ activeMeta?.unit ?? resultFiles[0].size_label }}</span>
        </div>
        <div v-else class="empty-state">项目目录中没有发现 FRD / VTU / DAT 结果文件。</div>
        <div class="axis-cluster">
          <i>X</i>
          <i>Y</i>
          <i>Z</i>
        </div>
      </div>

      <div v-if="activeMeta" class="field-scale">
        <span>0</span>
        <i :style="{ '--field-color': activeMeta.color }" />
        <span>{{ activeMeta.max }} {{ activeMeta.unit }}</span>
      </div>
    </article>

    <aside class="panel result-inspector">
      <div class="panel-title">
        <Icon icon="carbon:ibm-data-product-exchange" />
        <span>结果检查器</span>
      </div>

      <div class="file-stack">
        <button v-for="file in resultFiles" :key="file.path" :class="{ active: activeField === file.path }" @click="activeField = file.path">
          <Icon icon="carbon:document" />
          <span>
            <strong>{{ file.name }}</strong>
            <small>{{ file.type }} · {{ file.size_label }}</small>
          </span>
        </button>
        <div v-if="!resultFiles.length" class="empty-state">没有可检查的结果文件。</div>
      </div>

      <div class="slice-list">
        <div v-for="slice in slices" :key="slice.label">
          <span>{{ slice.label }}</span>
          <strong>{{ slice.value }}</strong>
        </div>
      </div>
    </aside>

    <article class="panel result-metrics">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:meter-alt" />
          <span>计算摘要</span>
        </div>
        <span class="mono-caption">真实文件扫描 · 证据可追溯</span>
      </div>
      <div class="metric-grid">
        <div v-for="item in metrics" :key="item.label" class="metric-card">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}<small>{{ item.unit }}</small></strong>
          <em>{{ item.hint }}</em>
        </div>
      </div>
      <div class="result-pipeline">
        <div>
          <strong>INP</strong>
          <small>{{ store.snapshot?.active_input ?? '未发现' }}</small>
        </div>
        <div>
          <strong>Docker</strong>
          <small>{{ store.snapshot?.docker.backend ?? '未连接' }}</small>
        </div>
        <div>
          <strong>CalculiX</strong>
          <small>{{ store.snapshot?.solvers[0]?.installed ? '已安装' : '未安装' }}</small>
        </div>
        <div>
          <strong>结果</strong>
          <small>{{ store.snapshot?.assets.result_files ?? 0 }} 个文件</small>
        </div>
        <div>
          <strong>诊断</strong>
          <small>{{ store.snapshot?.config.evidence_guard ? '证据护栏' : '未开启' }}</small>
        </div>
      </div>
    </article>
  </div>
</template>
