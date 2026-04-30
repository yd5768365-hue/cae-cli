<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Icon } from '@iconify/vue'
import { useAppStore } from '@/stores/app'
import { useCaeCli } from '@/composables/useCaeCli'

const store = useAppStore()
const cae = useCaeCli()

const isChecking = ref(false)
const pullingAlias = ref('')
const pullError = ref('')

const docker = computed(() => store.snapshot?.docker)
const dockerAvailable = computed(() => Boolean(docker.value?.available))
const wslDocker = computed(() => docker.value?.backend === 'wsl')
const images = computed(() => docker.value?.catalog.filter((image) => image.runnable).slice(0, 8) ?? [])
const solvers = computed(() => Array.from(new Set(images.value.map((image) => image.solver))))
const pulledCount = computed(() => images.value.filter((image) => image.status === 'pulled').length)

async function checkStatus() {
  isChecking.value = true
  await store.loadSnapshot()
  isChecking.value = false
}

async function pullImage(alias: string) {
  if (pullingAlias.value) return
  pullingAlias.value = alias
  pullError.value = ''
  const result = await cae.dockerPull(alias)
  if (!result.ok) {
    pullError.value = result.error?.message ?? '镜像拉取失败'
  }
  pullingAlias.value = ''
  await store.loadSnapshot()
}

onMounted(() => {
  if (!store.snapshot) store.loadSnapshot()
})
</script>

<template>
  <div class="page-grid docker-grid">
    <article class="panel page-panel docker-status-panel">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:container-software" />
          <span>Docker 环境</span>
        </div>
        <span class="status-pill" :class="{ live: dockerAvailable }">{{ docker?.backend ?? '未连接' }}</span>
      </div>

      <div class="docker-health" :class="{ ok: dockerAvailable }">
        <Icon :icon="dockerAvailable ? 'carbon:checkmark-filled' : 'carbon:close-filled'" />
        <span>
          <strong>{{ dockerAvailable ? 'Docker 已连接' : 'Docker 未连接' }}</strong>
          <small>{{ dockerAvailable ? (wslDocker ? 'WSL2 Docker' : 'Windows 原生 Docker') : docker?.error ?? '等待检测' }}</small>
        </span>
      </div>

      <div class="status-matrix">
        <div>
          <span>引擎</span>
          <strong>{{ wslDocker ? 'WSL2' : 'Native' }}</strong>
        </div>
        <div>
          <span>版本</span>
          <strong>{{ docker?.version ?? '-' }}</strong>
        </div>
        <div>
          <span>镜像</span>
          <strong>{{ pulledCount }}/{{ images.length }}</strong>
        </div>
        <div>
          <span>后端</span>
          <strong>{{ docker?.command?.join(' ') || '-' }}</strong>
        </div>
      </div>

      <div class="check-list">
        <div>
          <Icon :icon="docker?.use_wsl_paths ? 'carbon:checkmark-filled' : 'carbon:information-filled'" />
          <span>
            <strong>路径模式</strong>
            <small>{{ docker?.use_wsl_paths ? '/mnt/<drive> WSL 挂载路径' : '原生 Windows 路径' }}</small>
          </span>
        </div>
        <div>
          <Icon :icon="dockerAvailable ? 'carbon:checkmark-filled' : 'carbon:warning-filled'" />
          <span>
            <strong>本地镜像</strong>
            <small>{{ docker?.local_image_count ?? 0 }} 个 Docker 镜像可见</small>
          </span>
        </div>
      </div>
    </article>

    <article class="panel page-panel image-panel">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:catalog" />
          <span>镜像管理</span>
        </div>
        <button class="md-btn-outlined" @click="checkStatus">
          <Icon :icon="isChecking ? 'carbon:progress-bar' : 'carbon:renew'" :class="{ 'animate-pulse': isChecking }" />
          {{ isChecking ? '刷新中' : '刷新' }}
        </button>
      </div>

      <div class="image-grid">
        <article v-for="image in images" :key="image.alias" class="image-card">
          <div class="image-state" :class="pullingAlias === image.alias ? 'pulling' : image.status" />
          <span>
            <strong>{{ image.alias }}</strong>
            <small>{{ image.solver }} · {{ image.size ?? image.image }}</small>
          </span>
          <button
            :class="image.status === 'pulled' ? 'md-chip-active' : 'md-chip'"
            :disabled="image.status === 'pulled' || Boolean(pullingAlias)"
            @click="pullImage(image.alias)"
          >
            {{ image.status === 'pulled' ? '已拉取' : pullingAlias === image.alias ? '拉取中' : '拉取' }}
          </button>
        </article>
        <div v-if="!images.length" class="empty-state">没有可用的 Docker 镜像目录。</div>
      </div>
      <p v-if="pullError" class="diagnosis-error">{{ pullError }}</p>

      <div class="solver-tags">
        <span v-for="solver in solvers" :key="solver">{{ solver }}</span>
      </div>
    </article>

    <article class="panel page-panel docker-command-panel">
      <div class="panel-head">
        <div class="panel-title">
          <Icon icon="carbon:terminal" />
          <span>推荐命令</span>
        </div>
        <span class="mono-caption">一键复现当前环境</span>
      </div>
      <div class="command-copy">
        <code>cae docker status --json</code>
        <button title="复制"><Icon icon="carbon:copy" /></button>
      </div>
      <p>{{ dockerAvailable ? `Docker 命令: ${docker?.command?.join(' ')}` : docker?.error ?? 'Docker 当前不可用' }}</p>
    </article>
  </div>
</template>
