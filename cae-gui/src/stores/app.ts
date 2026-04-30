import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { useCaeCli } from '@/composables/useCaeCli'
import type { DiagnosisResult, GuiSnapshot, Project, SolveTask } from '@/types'

export const useAppStore = defineStore('app', () => {
  const cae = useCaeCli()
  const snapshot = ref<GuiSnapshot | null>(null)
  const snapshotLoading = ref(false)
  const snapshotError = ref('')
  const selectedInputPath = ref<string | null>(null)
  const projects = ref<Project[]>([])
  const solveTasks = ref<SolveTask[]>([])
  const diagnosisResult = ref<DiagnosisResult | null>(null)
  const activeProject = ref<Project | null>(null)
  const sidebarCollapsed = ref(false)

  const currentSolve = computed(() => solveTasks.value.find((task) => task.status === 'running'))

  const recentProjects = computed(() =>
    [...projects.value].sort(
      (a, b) => new Date(b.lastModified).getTime() - new Date(a.lastModified).getTime(),
    ),
  )

  function setActiveProject(project: Project) {
    activeProject.value = project
  }

  async function loadSnapshot(inpFile?: string) {
    if (snapshotLoading.value) return
    if (inpFile) {
      selectedInputPath.value = inpFile
    }
    snapshotLoading.value = true
    snapshotError.value = ''
    const result = await cae.guiSnapshot('E:\\cae-cli', selectedInputPath.value ?? undefined)
    snapshotLoading.value = false

    if (!result.ok || !result.data || typeof result.data === 'string') {
      snapshotError.value = result.error?.message ?? '无法读取 GUI 真实数据快照'
      return
    }

    const payload = result.data as GuiSnapshot
    snapshot.value = payload
    selectedInputPath.value = payload.active_input ?? selectedInputPath.value
    projects.value = payload.files.inputs
      .filter((file) => file.type === 'INP')
      .map((file, index) => ({
        id: file.path,
        name: file.stem,
        path: file.path,
        status:
          file.path === payload.active_input
            ? payload.inp.valid
              ? 'done'
              : 'error'
            : 'idle',
        lastModified: file.modified,
      }))
    activeProject.value =
      projects.value.find((project) => project.path === payload.active_input)
      ?? projects.value[0]
      ?? null
    solveTasks.value = payload.solve_history.map((item, index) => ({
      id: `${item.file}-${index}`,
      projectName: item.name,
      inputFile: payload.active_input ?? '',
      outputDir: payload.project.output_dir,
      status: item.status === '有结果' ? 'completed' : 'pending',
      progress: item.status === '有结果' ? 100 : 0,
      endTime: item.time,
      log: [item.file],
    }))
  }

  async function setActiveModel(modelName: string) {
    if (!modelName.trim()) return false
    const result = await cae.modelSet(modelName)
    if (!result.ok) {
      snapshotError.value = result.error?.message ?? '无法切换 AI 模型'
      return false
    }
    await loadSnapshot()
    return true
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
  }

  function addProject(project: Project) {
    projects.value.push(project)
  }

  function addSolveTask(task: SolveTask) {
    solveTasks.value.push(task)
  }

  function updateSolveTask(id: string, updates: Partial<SolveTask>) {
    const task = solveTasks.value.find((item) => item.id === id)
    if (task) {
      Object.assign(task, updates)
    }
  }

  function setDiagnosisResult(result: DiagnosisResult) {
    diagnosisResult.value = result
  }

  return {
    projects,
    solveTasks,
    snapshot,
    snapshotLoading,
    snapshotError,
    selectedInputPath,
    diagnosisResult,
    activeProject,
    sidebarCollapsed,
    currentSolve,
    recentProjects,
    loadSnapshot,
    setActiveModel,
    setActiveProject,
    toggleSidebar,
    addProject,
    addSolveTask,
    updateSolveTask,
    setDiagnosisResult,
  }
})
