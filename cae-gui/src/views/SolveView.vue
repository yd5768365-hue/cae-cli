<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import { useAppStore } from '@/stores/app'
import { useCaeCli } from '@/composables/useCaeCli'

const store = useAppStore()
const cae = useCaeCli()

const selectedInput = ref('examples/simple_beam.inp')
const outputDir = ref('')
const solverType = ref<'docker' | 'native'>('docker')
const isRunning = ref(false)
const isSelectingFile = ref(false)
const progress = ref(0)
const runLog = ref<string[]>(['等待求解任务...'])
const precheckError = ref('')

const solverCards = computed(() => [
  {
    key: 'docker',
    name: 'Docker CalculiX',
    desc: '调用 cae docker calculix 运行容器求解',
    icon: 'carbon:container-software',
    state: store.snapshot?.docker.available ? '可用' : '不可用',
  },
  {
    key: 'native',
    name: '本地 CalculiX',
    desc: '调用 cae solve 使用本地求解器',
    icon: 'carbon:terminal',
    state: store.snapshot?.solvers.find((solver) => solver.name === 'calculix')?.installed ? '可用' : '未安装',
  },
] as const)

const inputCandidates = computed(() => store.snapshot?.files.inputs.filter((file) => file.type === 'INP').slice(0, 4) ?? [])

const checks = computed(() => [
  { label: '输入文件', value: selectedInput.value || '未选择', ok: Boolean(selectedInput.value) },
  { label: '输出目录', value: outputDir.value || store.snapshot?.project.output_dir || '自动生成', ok: true },
  {
    label: '求解后端',
    value: solverType.value === 'docker' ? store.snapshot?.docker.backend ?? 'Docker' : '本地 ccx',
    ok:
      solverType.value === 'docker'
        ? Boolean(store.snapshot?.docker.available)
        : Boolean(store.snapshot?.solvers.some((solver) => solver.installed)),
  },
])

const history = computed(() =>
  store.solveTasks.map((task) => ({
    name: task.projectName,
    file: task.inputFile,
    status: task.status === 'completed' ? '完成' : task.status === 'failed' ? '失败' : '排队',
    time: task.endTime?.slice(11, 16) ?? task.startTime?.slice(11, 16) ?? '--:--',
  })),
)

async function startSolve() {
  if (!selectedInput.value || isRunning.value) return

  isRunning.value = true
  progress.value = 15
  runLog.value = [
    solverType.value === 'docker'
      ? `> cae docker calculix ${selectedInput.value}`
      : `> cae solve ${selectedInput.value}`,
  ]

  const result =
    solverType.value === 'docker'
      ? await cae.dockerCalculix(selectedInput.value, undefined, outputDir.value || undefined)
      : await cae.solve(selectedInput.value, outputDir.value || undefined)

  progress.value = result.ok ? 100 : 0
  if (typeof result.data === 'string' && result.data.trim()) {
    runLog.value.push(...result.data.trim().split(/\r?\n/))
  }
  if (!result.ok) {
    runLog.value.push(`失败: ${result.error?.message ?? '求解命令返回错误'}`)
  } else {
    runLog.value.push('完成: 求解命令已返回成功')
  }
  isRunning.value = false
  await store.loadSnapshot()
}

async function chooseInputFile() {
  isSelectingFile.value = true
  precheckError.value = ''
  const selected = await cae.pickInpFile(store.snapshot?.project_root ?? 'E:\\cae-cli')
  isSelectingFile.value = false

  if (!selected) {
    if (cae.error.value) {
      precheckError.value = `文件选择失败: ${cae.error.value}`
    }
    return
  }

  selectedInput.value = selected
  await store.loadSnapshot(selected)
}

async function selectCandidate(path: string) {
  selectedInput.value = path
  await store.loadSnapshot(path)
}

function stopSolve() {
  isRunning.value = false
  runLog.value.push('当前版本使用同步命令执行，无法安全中断已提交的外部求解进程。')
}

async function runPrecheck() {
  precheckError.value = ''
  runLog.value = [`> cae inp check ${selectedInput.value} --json`]
  const result = await cae.inpCheck(selectedInput.value, { json: true })
  if (!result.ok && !result.data) {
    precheckError.value = result.error?.message ?? '预检查失败'
    runLog.value.push(`失败: ${precheckError.value}`)
    return
  }
  const payload = result.data as { valid?: boolean; block_count?: number; unknown_keywords?: string[] }
  runLog.value.push(`valid=${payload.valid} blocks=${payload.block_count ?? 0}`)
  if (payload.unknown_keywords?.length) {
    runLog.value.push(`unknown_keywords=${payload.unknown_keywords.join(', ')}`)
  }
}

onMounted(() => {
  if (!store.snapshot) {
    store.loadSnapshot()
    return
  }
  selectedInput.value = store.snapshot.active_input ?? selectedInput.value
  outputDir.value = store.snapshot.project.output_dir
})

watch(
  () => store.snapshot,
  (snapshot) => {
    if (!snapshot) return
    selectedInput.value = snapshot.active_input ?? selectedInput.value
    outputDir.value = snapshot.project.output_dir
  },
)
</script>

<template>
  <div class="page-grid solve-grid">
    <article class="panel page-panel command-panel">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:launch" />
          <span>求解任务</span>
        </div>
        <span class="status-pill" :class="{ live: isRunning }">{{ isRunning ? '运行中' : '待启动' }}</span>
      </div>

      <label class="field-block">
        <span>输入文件</span>
        <div class="input-shell">
          <input v-model="selectedInput" type="text" placeholder="examples/simple_beam.inp" />
          <button title="选择文件" :disabled="isSelectingFile" @click="chooseInputFile">
            <Icon :icon="isSelectingFile ? 'carbon:progress-bar' : 'carbon:folder-open'" />
          </button>
        </div>
      </label>

      <label class="field-block">
        <span>输出目录</span>
        <div class="input-shell">
          <input v-model="outputDir" type="text" placeholder="results/beam" />
          <button title="选择目录"><Icon icon="carbon:folder-details" /></button>
        </div>
      </label>

      <div class="solver-picker">
        <button
          v-for="solver in solverCards"
          :key="solver.key"
          class="solver-card"
          :class="{ selected: solverType === solver.key }"
          @click="solverType = solver.key"
        >
          <Icon :icon="solver.icon" />
          <span>
            <strong>{{ solver.name }}</strong>
            <small>{{ solver.desc }}</small>
          </span>
          <em>{{ solver.state }}</em>
        </button>
      </div>

      <div class="action-strip">
        <button class="md-btn-filled" :disabled="!selectedInput" @click="isRunning ? stopSolve() : startSolve()">
          <Icon :icon="isRunning ? 'carbon:stop-filled' : 'carbon:play-filled-alt'" />
          {{ isRunning ? '中断' : '开始求解' }}
        </button>
        <button class="md-btn-outlined" @click="runPrecheck">
          <Icon icon="carbon:checkmark-outline" />
          预检查
        </button>
      </div>
      <p v-if="precheckError" class="diagnosis-error">{{ precheckError }}</p>
    </article>

    <article class="panel page-panel log-panel">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:terminal" />
          <span>运行日志</span>
        </div>
        <span class="mono-caption">{{ store.snapshot?.assets.log_files ?? 0 }} 个日志文件</span>
      </div>

      <div class="progress-track">
        <span :style="{ width: `${progress}%` }" />
      </div>

      <div class="terminal-window">
        <p
          v-for="(line, index) in runLog"
          :key="`${line}-${index}`"
          :class="{ command: line.startsWith('>'), success: line.startsWith('完成') || line.includes('收敛') }"
        >
          {{ line }}
        </p>
        <i v-if="isRunning" />
      </div>
    </article>

    <aside class="side-stack">
      <article class="panel page-panel compact-panel">
        <div class="panel-title">
          <Icon icon="carbon:document" />
          <span>输入候选</span>
        </div>
        <button
          v-for="file in inputCandidates"
          :key="file.path"
          class="precision-option"
          :class="{ selected: selectedInput === file.path }"
          @click="selectCandidate(file.path)"
        >
          <span />
          <strong>{{ file.name }}</strong>
          <small>{{ file.size_label }} · {{ file.modified }}</small>
        </button>
        <div v-if="!inputCandidates.length" class="empty-state">没有发现可求解的 INP 文件。</div>
      </article>

      <article class="panel page-panel compact-panel">
        <div class="panel-title">
          <Icon icon="carbon:task-complete" />
          <span>环境检查</span>
        </div>
        <div class="check-list">
          <div v-for="item in checks" :key="item.label">
            <Icon :icon="item.ok ? 'carbon:checkmark-filled' : 'carbon:warning-filled'" />
            <span>
              <strong>{{ item.label }}</strong>
              <small>{{ item.value }}</small>
            </span>
          </div>
        </div>
      </article>
    </aside>

    <article class="panel page-panel history-panel">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:recently-viewed" />
          <span>最近任务</span>
        </div>
        <span class="mono-caption">{{ history.length }} 条记录</span>
      </div>
      <div class="history-grid">
        <div v-for="item in history" :key="`${item.name}-${item.file}`" class="history-item">
          <span :class="{ failed: item.status === '失败' }" />
          <strong>{{ item.name }}</strong>
          <small>{{ item.file }}</small>
          <em>{{ item.status }} · {{ item.time }}</em>
        </div>
        <div v-if="!history.length" class="empty-state">尚未发现历史求解日志或结果文件。</div>
      </div>
    </article>
  </div>
</template>
