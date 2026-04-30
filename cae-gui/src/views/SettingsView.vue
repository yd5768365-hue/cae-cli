<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Icon } from '@iconify/vue'
import { useAppStore } from '@/stores/app'

const store = useAppStore()
const activeSection = ref<'general' | 'solver' | 'ai' | 'about'>('general')

const settings = ref({
  workspace: '',
  solverPath: '',
  defaultSolver: '',
  aiModel: '',
  language: 'zh-CN',
  evidenceGuard: false,
  dockerBackend: '',
})

const sections = [
  { key: 'general', label: '通用', icon: 'carbon:settings-adjust' },
  { key: 'solver', label: '求解器', icon: 'carbon:machine-learning-model' },
  { key: 'ai', label: 'AI', icon: 'carbon:watson-health-ai-status' },
  { key: 'about', label: '关于', icon: 'carbon:information' },
] as const

const modelOptions = computed(() => store.snapshot?.models.available ?? [])

function syncSettings() {
  const snapshot = store.snapshot
  if (!snapshot) return
  settings.value.workspace = snapshot.config.workspace ?? snapshot.project_root
  settings.value.solverPath = snapshot.config.solver_path ?? ''
  settings.value.defaultSolver = snapshot.config.default_solver
  settings.value.aiModel = snapshot.models.available.find((model) => model.active)?.value ?? snapshot.config.active_model ?? ''
  settings.value.evidenceGuard = snapshot.config.evidence_guard
  settings.value.dockerBackend = snapshot.docker.backend ?? '未连接'
}

async function changeAiModel() {
  if (!settings.value.aiModel) return
  await store.setActiveModel(settings.value.aiModel)
  syncSettings()
}

onMounted(async () => {
  if (!store.snapshot) {
    await store.loadSnapshot()
  }
  syncSettings()
})

watch(() => store.snapshot, syncSettings)
</script>

<template>
  <div class="page-grid settings-grid">
    <aside class="panel page-panel settings-nav">
      <button
        v-for="section in sections"
        :key="section.key"
        :class="{ active: activeSection === section.key }"
        @click="activeSection = section.key"
      >
        <Icon :icon="section.icon" />
        <span>{{ section.label }}</span>
      </button>
    </aside>

    <article class="panel page-panel settings-content">
      <template v-if="activeSection === 'general'">
        <div class="panel-head">
          <div class="panel-title">
            <Icon icon="carbon:settings-adjust" />
            <span>通用设置</span>
          </div>
        </div>

        <div class="setting-list">
          <label class="setting-row">
            <span>
              <strong>工作目录</strong>
              <small>缓存、求解临时文件与下载内容的位置</small>
            </span>
            <input v-model="settings.workspace" type="text" />
          </label>
          <label class="setting-row">
            <span>
              <strong>界面语言</strong>
              <small>默认跟随 cae-cli 中文输出风格</small>
            </span>
            <select v-model="settings.language">
              <option value="zh-CN">简体中文</option>
              <option value="en">English</option>
            </select>
          </label>
          <div class="notice-row">
            <Icon icon="carbon:data-vis-4" />
            <span>
              <strong>真实快照时间</strong>
              <small>{{ store.snapshot?.generated_at ?? '尚未读取' }}</small>
            </span>
          </div>
        </div>
      </template>

      <template v-if="activeSection === 'solver'">
        <div class="panel-head">
          <div class="panel-title">
            <Icon icon="carbon:machine-learning-model" />
            <span>求解器设置</span>
          </div>
        </div>

        <div class="setting-list">
          <label class="setting-row">
            <span>
              <strong>默认求解器</strong>
              <small>优先使用容器求解，避免安装源失败</small>
            </span>
            <select v-model="settings.defaultSolver">
              <option :value="settings.defaultSolver">{{ settings.defaultSolver || '未配置' }}</option>
            </select>
          </label>
          <label class="setting-row">
            <span>
              <strong>本地 ccx 路径</strong>
              <small>留空时只使用 Docker 工作流</small>
            </span>
            <input v-model="settings.solverPath" type="text" placeholder="自动检测 PATH" />
          </label>
          <label class="setting-row">
            <span>
              <strong>Docker 后端</strong>
              <small>Windows 推荐 WSL2 独立 Docker</small>
            </span>
            <select v-model="settings.dockerBackend">
              <option :value="settings.dockerBackend">{{ settings.dockerBackend || '未连接' }}</option>
            </select>
          </label>
        </div>
      </template>

      <template v-if="activeSection === 'ai'">
        <div class="panel-head">
          <div class="panel-title">
            <Icon icon="carbon:watson-health-ai-status" />
            <span>AI 诊断</span>
          </div>
        </div>

        <div class="setting-list">
          <label class="setting-row">
            <span>
              <strong>诊断模型</strong>
              <small>规则和参考案例优先，LLM 只做补充分析</small>
            </span>
            <select v-model="settings.aiModel" @change="changeAiModel">
              <option v-if="!modelOptions.length" value="">未发现本地模型</option>
              <option v-for="model in modelOptions" :key="`${model.source}-${model.value}`" :value="model.value">
                {{ model.name }}
              </option>
            </select>
          </label>
          <button class="setting-row toggle-line" @click="settings.evidenceGuard = !settings.evidenceGuard">
            <Icon icon="carbon:security" />
            <span>
              <strong>证据护栏</strong>
              <small>要求诊断结论引用输入或日志证据</small>
            </span>
            <i class="switch mini" :class="{ on: settings.evidenceGuard }"><span /></i>
          </button>
          <div class="notice-row">
            <Icon icon="carbon:warning-filled" />
            <span>
              <strong>AI 扩展未连接</strong>
              <small>{{ settings.aiModel ? '当前模型来自 cae-cli 配置。' : '当前仅启用规则与参考案例诊断。' }}</small>
            </span>
          </div>
        </div>
      </template>

      <template v-if="activeSection === 'about'">
        <div class="about-card">
          <div class="brand-mark static">
            <Icon icon="carbon:assembly-cluster" />
          </div>
          <span>
            <strong>cae-cli</strong>
            <small>Python CLI · Vue 3 GUI · Tauri 桌面壳</small>
          </span>
        </div>

        <div class="tech-grid">
          <div>
            <Icon icon="carbon:logo-python" />
            <span>后端</span>
            <strong>Python</strong>
          </div>
          <div>
            <Icon icon="carbon:logo-vue" />
            <span>前端</span>
            <strong>Vue 3</strong>
          </div>
          <div>
            <Icon icon="carbon:container-software" />
            <span>容器</span>
            <strong>Docker</strong>
          </div>
          <div>
            <Icon icon="carbon:report-data" />
            <span>诊断</span>
            <strong>规则 + AI</strong>
          </div>
        </div>
      </template>
    </article>
  </div>
</template>
