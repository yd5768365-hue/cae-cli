<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useCaeCli } from '@/composables/useCaeCli'

type CockpitDiagnosisIssue = {
  severity?: string
  category?: string
  message?: string
  evidence_line?: string | null
  evidence_score?: number | null
  evidence_source_trust?: number | null
  evidence_support_count?: number | null
  evidence_conflict?: string | null
  confidence?: 'high' | 'medium' | 'low' | string
  triage?: string
  suggestion?: string | null
}

type CockpitDiagnosisPayload = {
  success?: boolean
  issue_count?: number
  summary?: {
    confidence_counts?: Record<string, number>
    risk_score?: number
    risk_level?: string
    action_items?: string[]
    execution_plan?: Array<{
      confidence?: string
      action?: string
      evidence_line?: string | null
      triage?: string
    }>
  }
  issues?: CockpitDiagnosisIssue[]
  level1_issues?: CockpitDiagnosisIssue[]
  level2_issues?: CockpitDiagnosisIssue[]
  similar_cases?: Array<{ name?: string; similarity_score?: number }>
  ai_diagnosis?: unknown
  solver_run?: {
    primary_log?: string | null
    text_sources?: unknown[]
    artifacts?: {
      input_files?: string[]
      log_files?: string[]
      result_files?: string[]
    }
  }
  meta?: {
    inp_file?: string | null
    ai_enabled?: boolean
    routing_route?: string
    solver_status?: string
  }
  routing?: {
    recommended_next_action?: string
    classification_gaps?: string[]
  }
}

const router = useRouter()
const store = useAppStore()
const cae = useCaeCli()
const diagnosisPayload = ref<CockpitDiagnosisPayload | null>(null)
const diagnosisLoading = ref(false)
const diagnosisError = ref('')
const showConfidenceDetails = ref(false)

const snapshot = computed(() => store.snapshot)
const diagnosisIssues = computed(() => diagnosisPayload.value?.issues ?? [])

const projectStats = computed(() => {
  const assets = snapshot.value?.assets
  const docker = snapshot.value?.docker
  return [
    { label: '诊断规则', value: String(assets?.diagnosis_rules ?? 0), unit: '条', hint: '来自规则引擎源码' },
    { label: '参考案例', value: String(assets?.reference_cases ?? 0), unit: '组', hint: '来自 reference_cases.json' },
    { label: 'CalculiX 关键词', value: String(assets?.keywords ?? 0), unit: '个', hint: '来自 kw_list.json' },
    { label: 'Docker 后端', value: docker?.available ? docker.backend ?? '可用' : '不可用', unit: '', hint: docker?.version ?? docker?.error ?? '等待检测' },
  ]
})

const modelTree = computed(() => {
  const blocks = snapshot.value?.inp.blocks ?? []
  return blocks.slice(0, 9).map((block) => ({
    name: block.keyword,
    count: `${block.data_line_count} 行 · ${block.line_start}-${block.line_end}`,
    state: block.status === 'ok' ? '通过' : '需复核',
  }))
})

const pipeline = computed(() => {
  const data = snapshot.value
  const diagnosis = diagnosisPayload.value
  const summary = diagnosis?.summary
  const actionCount = summary?.action_items?.length ?? summary?.execution_plan?.length ?? 0
  const ruleHits = diagnosis?.level1_issues?.length ?? 0
  const caseHits = diagnosis?.similar_cases?.length ?? 0
  const hasDiagnosis = Boolean(diagnosis)
  const hasDiagnosisEvidence = Boolean(data?.active_input)
  return [
    { label: '证据抽取', detail: diagnosis?.meta?.inp_file ?? data?.active_input ?? '未选择', icon: 'carbon:data-vis-4', done: hasDiagnosisEvidence },
    { label: '规则命中', detail: hasDiagnosis ? `${ruleHits} 条` : '待运行', icon: 'carbon:rule', done: hasDiagnosis },
    { label: '案例召回', detail: hasDiagnosis ? `${caseHits} 组` : `${data?.assets.reference_cases ?? 0} 组可用`, icon: 'carbon:ibm-cloud-pak-business-automation', done: caseHits > 0 },
    { label: 'LLM 推理', detail: diagnosis?.meta?.ai_enabled ? '已启用' : '未启用', icon: 'carbon:ai-results', done: Boolean(diagnosis?.ai_diagnosis) },
    { label: '修正建议', detail: hasDiagnosis ? `${actionCount} 条` : '待生成', icon: 'carbon:tool-kit', done: actionCount > 0 },
  ]
})

const diagnosisConfidence = computed(() => {
  const payload = diagnosisPayload.value
  if (!payload) {
    return { score: 0, label: diagnosisLoading.value ? '诊断中' : '未运行', source: '等待 cae diagnose --json' }
  }

  const scores = diagnosisIssues.value
    .map((issue) => issue.evidence_score)
    .filter((score): score is number => typeof score === 'number')
  if (!scores.length) {
    return {
      score: payload.success ? 100 : 0,
      label: payload.success ? '无问题' : '无证据分',
      source: '来自 cae diagnose --json',
    }
  }

  const score = Math.round((scores.reduce((sum, item) => sum + item, 0) / scores.length) * 100)
  return { score, label: '证据均分', source: '来自 cae diagnose --json' }
})

const confidenceBreakdown = computed(() => {
  const payload = diagnosisPayload.value
  const summary = payload?.summary
  const confidenceCounts = summary?.confidence_counts ?? {}
  return [
    { label: '高置信', value: String(confidenceCounts.high ?? 0), hint: '证据分与来源可信度均较高' },
    { label: '中置信', value: String(confidenceCounts.medium ?? 0), hint: '证据明确，但仍建议复核上下文' },
    { label: '低置信', value: String(confidenceCounts.low ?? 0), hint: '证据不足或存在冲突' },
    { label: '风险评分', value: `${summary?.risk_score ?? 0}/100`, hint: summary?.risk_level ?? '未运行' },
  ]
})

const confidenceSources = computed(() => {
  const payload = diagnosisPayload.value
  const artifacts = payload?.solver_run?.artifacts
  return [
    { label: '规则层命中', value: String(payload?.level1_issues?.length ?? 0), hint: 'L1 规则诊断真实结果' },
    { label: '案例召回', value: String(payload?.similar_cases?.length ?? 0), hint: payload?.similar_cases?.[0]?.name ?? '暂无匹配案例' },
    { label: '文本证据', value: String(payload?.solver_run?.text_sources?.length ?? 0), hint: payload?.solver_run?.primary_log ?? '暂无主日志' },
    { label: '结果/日志', value: String((artifacts?.result_files?.length ?? 0) + (artifacts?.log_files?.length ?? 0)), hint: '来自 solver_run.artifacts' },
  ]
})

const evidenceFiles = computed(() => [
  ...(snapshot.value?.files.results ?? []),
  ...(snapshot.value?.files.logs ?? []),
])

const confidenceSummaryText = computed(() => {
  if (diagnosisError.value) return diagnosisError.value
  if (diagnosisLoading.value) return '正在读取真实诊断输出...'
  return diagnosisPayload.value?.routing?.recommended_next_action ?? diagnosisPayload.value?.summary?.action_items?.[0] ?? '点击查看依据，展开每条诊断证据。'
})

function go(path: string) {
  router.push(path)
}

async function runCockpitDiagnosis() {
  const input = snapshot.value?.active_input
  if (!input || diagnosisLoading.value) return

  diagnosisLoading.value = true
  diagnosisError.value = ''
  const result = await cae.diagnose(input, { json: true })
  diagnosisLoading.value = false

  if (!result.ok && !result.data) {
    diagnosisPayload.value = null
    diagnosisError.value = result.error?.message ?? '诊断命令执行失败'
    return
  }

  if (!result.data || typeof result.data === 'string') {
    diagnosisPayload.value = null
    diagnosisError.value = '诊断命令没有返回结构化 JSON'
    return
  }

  diagnosisPayload.value = result.data as CockpitDiagnosisPayload
  if (!result.ok) {
    diagnosisError.value = result.error?.message ?? '诊断完成，但命令返回非零退出码'
  }
}

onMounted(async () => {
  if (!store.snapshot) await store.loadSnapshot()
  await runCockpitDiagnosis()
})

watch(() => snapshot.value?.active_input, runCockpitDiagnosis)
</script>

<template>
  <div class="engineering-dashboard">
    <article class="panel overview-hero">
      <div>
        <span class="section-label">AI DIAGNOSIS COCKPIT</span>
        <h2>{{ snapshot?.project.input_file ?? '未发现 INP 文件' }} 诊断驾驶舱</h2>
        <p>当前页面来自真实项目快照：INP、求解日志和结果文件只显示本机扫描到的证据。</p>
      </div>
      <button class="command-button" @click="go('/diagnose')">
        <Icon icon="carbon:ai-results" />
        进入诊断
      </button>
    </article>

    <article class="panel readiness-panel">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:meter" />
          <span>诊断置信度</span>
        </div>
        <button class="icon-text-button" :disabled="diagnosisLoading" @click="runCockpitDiagnosis">
          <Icon :icon="diagnosisLoading ? 'carbon:progress-bar' : 'carbon:renew'" />
          刷新
        </button>
      </div>
      <div class="readiness-ring" :style="{ '--score': `${diagnosisConfidence.score}%` }">
        <strong>{{ diagnosisConfidence.score }}%</strong>
        <span>{{ diagnosisConfidence.label }}</span>
      </div>
      <div class="readiness-notes">
        <span><i /> {{ diagnosisConfidence.source }}</span>
        <span><i class="warn" /> {{ confidenceSummaryText }}</span>
      </div>
      <button class="md-btn-outlined wide-button confidence-toggle" @click="showConfidenceDetails = !showConfidenceDetails">
        <Icon icon="carbon:chart-evaluation" />
        {{ showConfidenceDetails ? '收起依据' : '查看依据' }}
      </button>
    </article>

    <article v-if="showConfidenceDetails" class="panel confidence-detail-panel">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:chart-evaluation" />
          <span>置信度依据</span>
        </div>
        <span class="mono-caption">{{ diagnosisPayload?.meta?.inp_file ?? snapshot?.active_input ?? '未选择 INP' }}</span>
      </div>

      <div class="confidence-matrix">
        <div v-for="item in confidenceBreakdown" :key="item.label">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <em>{{ item.hint }}</em>
        </div>
      </div>

      <div class="confidence-matrix compact">
        <div v-for="item in confidenceSources" :key="item.label">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}</strong>
          <em>{{ item.hint }}</em>
        </div>
      </div>

      <div class="confidence-issue-list">
        <article v-for="(issue, index) in diagnosisIssues" :key="`${issue.category}-${index}`">
          <div>
            <strong>{{ issue.category ?? '诊断项' }} · {{ issue.confidence ?? 'unknown' }}</strong>
            <span>{{ issue.triage ?? issue.severity ?? '待复核' }}</span>
          </div>
          <p>{{ issue.message }}</p>
          <code v-if="issue.evidence_line">{{ issue.evidence_line }}</code>
          <div class="confidence-bars">
            <span>
              evidence_score
              <i :style="{ width: `${Math.round((issue.evidence_score ?? 0) * 100)}%` }" />
              <b>{{ Math.round((issue.evidence_score ?? 0) * 100) }}%</b>
            </span>
            <span>
              source_trust
              <i :style="{ width: `${Math.round((issue.evidence_source_trust ?? 0) * 100)}%` }" />
              <b>{{ Math.round((issue.evidence_source_trust ?? 0) * 100) }}%</b>
            </span>
            <em>support={{ issue.evidence_support_count ?? 0 }}{{ issue.evidence_conflict ? ` · conflict=${issue.evidence_conflict}` : '' }}</em>
          </div>
        </article>
        <div v-if="!diagnosisIssues.length" class="empty-state">
          {{ diagnosisLoading ? '正在生成真实置信度依据...' : '暂无诊断项，当前输入未产生可展开的置信度明细。' }}
        </div>
      </div>
    </article>

    <article class="panel model-tree-panel">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:tree-view" />
          <span>INP 结构树</span>
        </div>
        <span class="mono-caption">CalculiX</span>
      </div>
      <div class="keyword-tree">
        <button v-for="item in modelTree" :key="item.name">
          <code>{{ item.name }}</code>
          <span>{{ item.count }}</span>
          <em :class="{ warn: item.state === '需复核' }">{{ item.state }}</em>
        </button>
        <div v-if="!modelTree.length" class="empty-state">没有可显示的 INP 结构。</div>
      </div>
    </article>

    <article class="panel pipeline-board">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:flow" />
          <span>诊断流水线</span>
        </div>
        <span class="mono-caption">Evidence → Rules → Cases → LLM</span>
      </div>
      <div class="cae-pipeline">
        <button v-for="step in pipeline" :key="step.label" :class="{ done: step.done }">
          <Icon :icon="step.icon" />
          <span>{{ step.label }}</span>
          <small>{{ step.detail }}</small>
        </button>
      </div>
    </article>

    <article class="panel stats-board">
      <div class="panel-title">
        <Icon icon="carbon:data-table" />
        <span>项目资产</span>
      </div>
      <div class="asset-grid">
        <div v-for="item in projectStats" :key="item.label">
          <span>{{ item.label }}</span>
          <strong>{{ item.value }}<small>{{ item.unit }}</small></strong>
          <em>{{ item.hint }}</em>
        </div>
      </div>
    </article>

    <article class="panel residual-board">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:chart-line" />
          <span>运行证据</span>
        </div>
        <span class="mono-caption">{{ evidenceFiles.length }} 个文件</span>
      </div>
      <div v-if="evidenceFiles.length" class="file-stack">
        <button v-for="file in evidenceFiles.slice(0, 4)" :key="file.path">
          <Icon icon="carbon:document" />
          <span>
            <strong>{{ file.name }}</strong>
            <small>{{ file.type }} · {{ file.size_label }}</small>
          </span>
        </button>
      </div>
      <div v-else class="empty-state">尚未发现求解日志或结果文件。</div>
    </article>
  </div>
</template>
