<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import type { DiagnosisIssue } from '@/types'
import { useCaeCli } from '@/composables/useCaeCli'
import { useAppStore } from '@/stores/app'

type CliDiagnosisIssue = {
  severity?: string
  category?: string
  title?: string
  message?: string
  evidence_line?: string | null
  evidence_score?: number | null
  suggestion?: string | null
}

type CliDiagnosisPayload = {
  success?: boolean
  issue_count?: number
  summary?: {
    by_severity?: Record<string, number>
    execution_plan?: Array<{
      category?: string
      severity?: string
      action?: string
      evidence_line?: string | null
    }>
  }
  issues?: CliDiagnosisIssue[]
  level1_issues?: CliDiagnosisIssue[]
  level2_issues?: CliDiagnosisIssue[]
  ai_diagnosis?: unknown
  similar_cases?: unknown[]
  solver_run?: {
    artifacts?: {
      input_files?: string[]
      log_files?: string[]
      result_files?: string[]
    }
    text_sources?: unknown[]
  }
  meta?: {
    inp_file?: string | null
    results_dir?: string | null
    ai_enabled?: boolean
  }
  routing?: {
    recommended_next_action?: string
  }
}

const cae = useCaeCli()
const store = useAppStore()
const isRunning = ref(false)
const isSelectingFile = ref(false)
const filterSeverity = ref<'all' | DiagnosisIssue['severity']>('all')
const diagnosisPath = ref('examples\\simple_beam.inp')
const diagnosisPayload = ref<CliDiagnosisPayload | null>(null)
const diagnosisError = ref('')

const issues = ref<DiagnosisIssue[]>([])

const severityColors: Record<DiagnosisIssue['severity'], { bg: string; text: string; icon: string; label: string }> = {
  error: { bg: 'rgba(251, 113, 133, 0.12)', text: 'var(--red)', icon: 'carbon:error-filled', label: '错误' },
  warning: { bg: 'rgba(245, 184, 75, 0.12)', text: 'var(--amber)', icon: 'carbon:warning-filled', label: '警告' },
  info: { bg: 'rgba(56, 213, 255, 0.10)', text: 'var(--cyan)', icon: 'carbon:information-filled', label: '建议' },
}

const filterTabs = [
  { key: 'all', label: '全部' },
  { key: 'error', label: '错误' },
  { key: 'warning', label: '警告' },
  { key: 'info', label: '建议' },
] as const

const evidenceSources = computed(() => {
  const payload = diagnosisPayload.value
  const artifacts = payload?.solver_run?.artifacts
  const inpEvidence = issues.value.filter((issue) =>
    issue.evidenceLine?.toLowerCase().includes('.inp'),
  ).length
  return [
    {
      label: 'INP 证据',
      value: String(inpEvidence || artifacts?.input_files?.length || store.snapshot?.assets.input_files || 0),
      hint: payload?.meta?.inp_file ?? store.snapshot?.active_input ?? diagnosisPath.value,
      icon: 'carbon:document',
    },
    {
      label: '日志证据',
      value: String((artifacts?.log_files?.length ?? 0) + (payload?.solver_run?.text_sources?.length ?? 0)),
      hint: '残差、迭代、退出码',
      icon: 'carbon:terminal',
    },
    {
      label: '参考案例',
      value: String(payload?.similar_cases?.length ?? store.snapshot?.assets.reference_cases ?? 0),
      hint: '相似算例召回',
      icon: 'carbon:ibm-cloud-pak-business-automation',
    },
    { label: '关键词库', value: String(store.snapshot?.assets.keywords ?? 0), hint: 'CalculiX schema', icon: 'carbon:catalog' },
  ]
})

const aiLayers = computed(() => [
  {
    name: 'L1 规则引擎',
    value: String(diagnosisPayload.value?.level1_issues?.length ?? 0),
    state: diagnosisPayload.value ? `命中 ${diagnosisPayload.value?.level1_issues?.length ?? 0} 条` : '等待运行',
    active: Boolean(diagnosisPayload.value),
  },
  {
    name: 'L2 案例检索',
    value: String(diagnosisPayload.value?.similar_cases?.length ?? store.snapshot?.assets.reference_cases ?? 0),
    state: diagnosisPayload.value
      ? `匹配 ${diagnosisPayload.value?.similar_cases?.length ?? 0} 组`
      : `案例库 ${store.snapshot?.assets.reference_cases ?? 0} 组`,
    active: Boolean(diagnosisPayload.value),
  },
  {
    name: 'L3 LLM 推理',
    value: diagnosisPayload.value?.meta?.ai_enabled ? 'ON' : 'OFF',
    state: diagnosisPayload.value?.ai_diagnosis ? '已生成' : '未启用',
    active: Boolean(diagnosisPayload.value?.ai_diagnosis),
  },
])

const reasoningTrace = computed(() => {
  const plan = diagnosisPayload.value?.summary?.execution_plan
  if (plan?.length) {
    return plan.slice(0, 4).map((item) => ({
      step: item.category ?? item.severity ?? '诊断步骤',
      detail: item.action ?? item.evidence_line ?? '查看证据并确认修正动作',
    }))
  }
  return [
    { step: '证据抽取', detail: store.snapshot?.active_input ?? '等待真实诊断结果' },
    { step: '规则匹配', detail: `规则库 ${store.snapshot?.assets.diagnosis_rules ?? 0} 条` },
    { step: '案例召回', detail: `参考案例 ${store.snapshot?.assets.reference_cases ?? 0} 组` },
    { step: '修正建议', detail: '运行后显示可执行建议' },
  ]
})

const filteredIssues = computed(() =>
  filterSeverity.value === 'all'
    ? issues.value
    : issues.value.filter((issue) => issue.severity === filterSeverity.value),
)

const severityCount = computed(() => ({
  error: issues.value.filter((issue) => issue.severity === 'error').length,
  warning: issues.value.filter((issue) => issue.severity === 'warning').length,
  info: issues.value.filter((issue) => issue.severity === 'info').length,
}))

const confidence = computed(() => {
  if (issues.value.length === 0) {
    return diagnosisPayload.value?.success ? 100 : 0
  }
  const score = issues.value.reduce((sum, issue) => sum + (issue.evidenceScore ?? 0), 0)
  return Math.round((score / issues.value.length) * 100)
})

const diagnosisErrorSummary = computed(() => {
  const text = diagnosisError.value.trim()
  if (!text) {
    return ''
  }
  if (text.includes('program not allowed on the configured shell scope')) {
    return '桌面权限未放行 cae 命令，请使用最新构建的桌面版重新运行诊断。'
  }
  const firstLine = text.split(/\r?\n/).find(Boolean) ?? text
  return firstLine.length > 150 ? `${firstLine.slice(0, 147)}...` : firstLine
})

function normalizeSeverity(value: string | undefined): DiagnosisIssue['severity'] {
  if (value === 'error' || value === 'warning' || value === 'info') {
    return value
  }
  return 'info'
}

function mapCliIssue(issue: CliDiagnosisIssue, index: number): DiagnosisIssue {
  return {
    id: String(index + 1),
    severity: normalizeSeverity(issue.severity),
    category: issue.category ?? issue.title ?? '诊断',
    message: issue.message ?? issue.title ?? '诊断项缺少消息',
    evidenceLine: issue.evidence_line ?? undefined,
    evidenceScore: typeof issue.evidence_score === 'number' ? issue.evidence_score : undefined,
    suggestion: issue.suggestion ?? undefined,
  }
}

async function runDiagnose() {
  isRunning.value = true
  diagnosisError.value = ''
  const result = await cae.diagnose(diagnosisPath.value, { json: true })

  if (!result.ok && !result.data) {
    diagnosisError.value = result.error?.message ?? '诊断命令执行失败'
    isRunning.value = false
    return
  }

  if (!result.data || typeof result.data === 'string') {
    diagnosisError.value = '诊断命令没有返回结构化 JSON'
    isRunning.value = false
    return
  }

  const payload = result.data as CliDiagnosisPayload
  diagnosisPayload.value = payload
  issues.value = (payload.issues ?? []).map(mapCliIssue)
  store.setDiagnosisResult({
    issues: issues.value,
    summary: `${issues.value.length} 个真实诊断项`,
    timestamp: new Date().toISOString(),
  })

  if (!result.ok) {
    diagnosisError.value = result.error?.message ?? '诊断完成，但命令返回非零退出码'
  }

  isRunning.value = false
}

async function chooseInpFile() {
  isSelectingFile.value = true
  diagnosisError.value = ''
  const selected = await cae.pickInpFile(store.snapshot?.project_root ?? 'E:\\cae-cli')
  isSelectingFile.value = false

  if (!selected) {
    if (cae.error.value) {
      diagnosisError.value = `文件选择失败: ${cae.error.value}`
    }
    return
  }

  diagnosisPath.value = selected
  diagnosisPayload.value = null
  issues.value = []
  await store.loadSnapshot(selected)
  syncPathFromSnapshot()
  await runDiagnose()
}

function syncPathFromSnapshot() {
  if (store.snapshot?.active_input) {
    diagnosisPath.value = store.snapshot.active_input.replaceAll('/', '\\')
  }
}

onMounted(async () => {
  if (!store.snapshot) {
    await store.loadSnapshot()
  }
  syncPathFromSnapshot()
  if (diagnosisPath.value) {
    runDiagnose()
  }
})

watch(() => store.snapshot?.active_input, syncPathFromSnapshot)
</script>

<template>
  <div class="ai-diagnosis-workbench">
    <article class="panel ai-hero-panel">
      <div>
        <span class="section-label">AI DIAGNOSIS CORE</span>
        <h2>智能诊断中枢</h2>
        <div class="diagnosis-runner">
          <input v-model="diagnosisPath" type="text" />
          <button
            type="button"
            title="选择 INP 文件"
            :disabled="isRunning || isSelectingFile"
            @click="chooseInpFile"
          >
            <Icon :icon="isSelectingFile ? 'carbon:progress-bar' : 'carbon:folder-open'" />
            {{ isSelectingFile ? '选择中' : '选择文件' }}
          </button>
        </div>
        <p v-if="diagnosisErrorSummary" class="diagnosis-error">{{ diagnosisErrorSummary }}</p>
        <div class="ai-mode-row">
          <span>规则优先</span>
          <span>案例召回</span>
          <span>LLM 补充推理</span>
          <span>证据护栏</span>
        </div>
      </div>
      <div class="ai-score-card">
        <strong>{{ confidence }}%</strong>
        <span>证据置信度</span>
        <button class="command-button" :disabled="isRunning" @click="runDiagnose">
          <Icon :icon="isRunning ? 'carbon:progress-bar' : 'carbon:ai-results'" :class="{ 'animate-pulse': isRunning }" />
          {{ isRunning ? '诊断中' : '运行真实诊断' }}
        </button>
      </div>
    </article>

    <article class="panel evidence-board">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:data-vis-4" />
          <span>证据输入</span>
        </div>
        <span class="mono-caption">{{ store.snapshot?.active_input ?? diagnosisPath }}</span>
      </div>
      <div class="evidence-grid">
        <div v-for="item in evidenceSources" :key="item.label">
          <Icon :icon="item.icon" />
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <em>{{ item.hint }}</em>
        </div>
      </div>
    </article>

    <article class="panel issue-board">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:report-data" />
          <span>诊断结论</span>
        </div>
        <div class="chip-row">
          <button
            v-for="tab in filterTabs"
            :key="tab.key"
            :class="filterSeverity === tab.key ? 'md-chip-active' : 'md-chip'"
            @click="filterSeverity = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>
      </div>

      <div class="issue-list">
        <article v-for="issue in filteredIssues" :key="issue.id" class="issue-card" :style="{ background: severityColors[issue.severity].bg }">
          <Icon :icon="severityColors[issue.severity].icon" :style="{ color: severityColors[issue.severity].text }" />
          <div>
            <div class="issue-meta">
              <span :style="{ color: severityColors[issue.severity].text }">
                {{ severityColors[issue.severity].label }} · {{ issue.category }}
              </span>
              <em>证据 {{ ((issue.evidenceScore ?? 0) * 100).toFixed(0) }}%</em>
            </div>
            <strong>{{ issue.message }}</strong>
            <code v-if="issue.evidenceLine">{{ issue.evidenceLine }}</code>
            <p v-if="issue.suggestion">{{ issue.suggestion }}</p>
          </div>
        </article>
        <div v-if="!filteredIssues.length" class="empty-state">尚未生成真实诊断结论。</div>
      </div>
    </article>

    <aside class="panel ai-engine-panel">
      <div class="panel-title">
        <Icon icon="carbon:machine-learning-model" />
        <span>诊断引擎</span>
      </div>
      <div class="ai-layer-stack">
        <div v-for="layer in aiLayers" :key="layer.name" :class="{ active: layer.active }">
          <span>{{ layer.name }}</span>
          <strong>{{ layer.value }}</strong>
          <em>{{ layer.state }}</em>
        </div>
      </div>
      <div class="severity-stack compact">
        <div>
          <span class="danger" />
          <strong>错误</strong>
          <em>{{ severityCount.error }}</em>
        </div>
        <div>
          <span class="warn" />
          <strong>警告</strong>
          <em>{{ severityCount.warning }}</em>
        </div>
        <div>
          <span />
          <strong>建议</strong>
          <em>{{ severityCount.info }}</em>
        </div>
      </div>
    </aside>

    <article class="panel reasoning-board">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:flow-data" />
          <span>推理链</span>
        </div>
        <span class="mono-caption">Evidence → Rules → Cases → Fix</span>
      </div>
      <div class="reasoning-steps">
        <div v-for="(item, index) in reasoningTrace" :key="item.step">
          <span>{{ index + 1 }}</span>
          <strong>{{ item.step }}</strong>
          <small>{{ item.detail }}</small>
        </div>
      </div>
    </article>
  </div>
</template>
