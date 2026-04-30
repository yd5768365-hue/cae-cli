<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Icon } from '@iconify/vue'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const store = useAppStore()
const isSwitchingModel = ref(false)

const navItems = [
  { key: 'diagnose', label: 'AI 诊断', hint: '规则 + 案例库 + LLM', icon: 'carbon:ai-results', route: '/diagnose' },
  { key: 'project', label: '诊断驾驶舱', hint: '证据与模型状态', icon: 'carbon:ibm-engineering-systems-design-rhapsody', route: '/project' },
  { key: 'solve', label: '求解证据', hint: 'CalculiX / Docker 日志', icon: 'carbon:play-filled-alt', route: '/solve' },
  { key: 'viewer', label: '结果证据', hint: 'FRD / VTU / DAT', icon: 'carbon:chart-3d', route: '/viewer' },
  { key: 'docker', label: '容器环境', hint: 'WSL2 Docker', icon: 'carbon:container-software', route: '/docker' },
  { key: 'settings', label: '诊断设置', hint: '模型与证据护栏', icon: 'carbon:settings', route: '/settings' },
]

const activeItem = computed(() => {
  return navItems.find((item) => route.path.startsWith(item.route)) ?? navItems[0]
})

const modelOptions = computed(() => store.snapshot?.models.available ?? [])
const activeModelValue = computed(
  () => modelOptions.value.find((model) => model.active)?.value ?? store.snapshot?.models.active ?? store.snapshot?.config.active_model ?? '',
)
const evidenceState = computed(() => (store.snapshot?.config.evidence_guard ? '证据护栏开启' : '证据护栏关闭'))

function navigate(path: string) {
  router.push(path)
}

async function controlWindow(action: 'minimize' | 'maximize' | 'close') {
  try {
    const { getCurrentWindow } = await import('@tauri-apps/api/window')
    const win = getCurrentWindow()
    if (action === 'minimize') await win.minimize()
    if (action === 'maximize') await win.toggleMaximize()
    if (action === 'close') await win.close()
  } catch {
    // 浏览器预览环境没有 Tauri 窗口 API。
  }
}

async function changeModel(event: Event) {
  const value = (event.target as HTMLSelectElement).value
  if (!value || value === activeModelValue.value) return
  isSwitchingModel.value = true
  await store.setActiveModel(value)
  isSwitchingModel.value = false
}

onMounted(() => {
  store.loadSnapshot()
})
</script>

<template>
  <div class="app-shell">
    <header class="window-bar" data-tauri-drag-region>
      <div class="window-title" data-tauri-drag-region>
        <strong>cae-cli</strong>
        <span>AI 诊断工作台</span>
      </div>

      <div class="environment-strip" data-tauri-drag-region>
        <span><Icon icon="carbon:folder" /> {{ store.snapshot?.project_root ?? 'E:\\cae-cli' }}</span>
        <span><Icon icon="carbon:ai-results" /> 规则 + 案例 + LLM</span>
        <span><Icon icon="carbon:security" /> {{ evidenceState }}</span>
      </div>

      <div class="window-actions">
        <button class="window-button" title="最小化" @click="controlWindow('minimize')">
          <Icon icon="carbon:subtract" />
        </button>
        <button class="window-button" title="最大化" @click="controlWindow('maximize')">
          <Icon icon="carbon:maximize" />
        </button>
        <button class="window-button window-close" title="关闭" @click="controlWindow('close')">
          <Icon icon="carbon:close" />
        </button>
      </div>
    </header>

    <div class="workspace-shell">
      <aside class="side-rail">
        <button class="brand-mark" title="cae-cli" @click="navigate('/diagnose')">
          <Icon icon="carbon:ai-results" />
          <span>
            <strong>AI Diagnosis</strong>
            <small>Evidence → Reasoning → Fix</small>
          </span>
        </button>

        <div class="project-card">
          <span>当前工程</span>
          <strong>{{ store.activeProject?.name ?? '未选择工程' }}</strong>
          <small>{{ store.activeProject?.path ?? '请选择 .inp 文件' }}</small>
        </div>

        <nav class="nav-stack">
          <button
            v-for="item in navItems"
            :key="item.key"
            class="nav-button"
            :class="{ active: activeItem.key === item.key }"
            @click="navigate(item.route)"
          >
            <Icon :icon="item.icon" />
            <span>
              <strong>{{ item.label }}</strong>
              <small>{{ item.hint }}</small>
            </span>
          </button>
        </nav>
      </aside>

      <main class="main-stage">
        <div class="stage-heading">
          <div>
            <span class="stage-kicker">CAE-CLI AI DIAGNOSIS</span>
            <h1>{{ activeItem.label }}</h1>
            <p>{{ activeItem.hint }}</p>
          </div>

          <div class="heading-actions">
            <span class="state-chip ready"><Icon icon="carbon:checkmark-filled" /> {{ store.snapshot ? '真实快照已加载' : '读取真实快照' }}</span>
            <label class="model-select-chip" title="切换 AI 诊断模型">
              <Icon icon="carbon:machine-learning-model" />
              <select :value="activeModelValue" :disabled="isSwitchingModel || !modelOptions.length" @change="changeModel">
                <option v-if="!modelOptions.length" value="">未发现本地模型</option>
                <option v-for="model in modelOptions" :key="`${model.source}-${model.value}`" :value="model.value">
                  {{ model.name }}
                </option>
              </select>
            </label>
          </div>
        </div>

        <section class="stage-content">
          <router-view v-slot="{ Component }">
            <transition name="soft-fade" mode="out-in">
              <component :is="Component" />
            </transition>
          </router-view>
        </section>
      </main>
    </div>
  </div>
</template>
