export interface Project {
  id: string
  name: string
  path: string
  status: 'idle' | 'solving' | 'done' | 'error'
  lastModified: string
}

export interface SolveTask {
  id: string
  projectName: string
  inputFile: string
  outputDir: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  startTime?: string
  endTime?: string
  log?: string[]
}

export interface DiagnosisIssue {
  id: string
  severity: 'error' | 'warning' | 'info'
  category: string
  message: string
  evidenceLine?: string
  evidenceScore?: number
  suggestion?: string
}

export interface DiagnosisResult {
  issues: DiagnosisIssue[]
  summary: string
  timestamp: string
}

export interface ViewerResult {
  name: string
  type: 'frd' | 'dat' | 'vtu'
  path: string
  size: number
}

export interface SidebarItem {
  key: string
  label: string
  icon: string
  route: string
}

export interface GuiFileEntry {
  name: string
  stem: string
  path: string
  type: string
  size: number
  size_label: string
  modified: string
}

export interface GuiInpBlock {
  keyword: string
  name: string | null
  line_start: number
  line_end: number
  data_line_count: number
  status: 'ok' | 'needs_review'
  issues: Array<{ code: string; message: string }>
}

export interface GuiModelEntry {
  name: string
  value: string
  source: 'models_dir' | 'legacy_models_dir' | 'project_models' | 'ollama' | 'config' | string
  path: string | null
  size_label: string | null
  modified: string | null
  active: boolean
}

export interface GuiSnapshot {
  success: boolean
  generated_at: string
  project_root: string
  active_input: string | null
  project: {
    name: string
    input_file: string | null
    output_dir: string
  }
  config: {
    config_dir: string
    data_dir: string
    solvers_dir: string
    models_dir: string
    workspace: string | null
    default_solver: string
    default_output_dir: string
    solver_path: string | null
    active_model: string | null
    evidence_guard: boolean
  }
  models: {
    active: string | null
    available: GuiModelEntry[]
  }
  assets: {
    input_files: number
    result_files: number
    log_files: number
    geometry_files: number
    reference_cases: number
    keywords: number
    diagnosis_rules: number
  }
  files: {
    inputs: GuiFileEntry[]
    results: GuiFileEntry[]
    logs: GuiFileEntry[]
    geometry: GuiFileEntry[]
  }
  inp: {
    available: boolean
    valid: boolean
    file: string | null
    error: string | null
    block_count?: number
    keyword_count: Record<string, number>
    unknown_keywords?: string[]
    blocks: GuiInpBlock[]
    node_count: number
    element_count: number
    material_count: number
    step_count: number
    boundary_count: number
  }
  docker: {
    available: boolean
    version: string | null
    backend: string | null
    command: string[]
    use_wsl_paths: boolean
    error: string | null
    local_images: string[]
    local_image_count: number
    catalog: Array<{
      alias: string
      image: string
      solver: string
      description: string
      maturity: string
      runnable: boolean
      status: 'pulled' | 'available'
      size: string | null
    }>
  }
  solvers: Array<{
    name: string
    installed: boolean
    version: string | null
    formats: string[]
    description: string
  }>
  viewer: {
    has_results: boolean
    fields: Array<{ key: string; label: string; unit: string; max: string; color: string }>
    metrics: Array<{ label: string; value: number | string; unit: string; hint: string }>
  }
  solve_history: Array<{ name: string; file: string; status: string; time: string }>
}
