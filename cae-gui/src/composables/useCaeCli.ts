import { ref } from 'vue'

interface CommandResult<T = unknown> {
  ok: boolean
  data?: T
  error?: {
    code: string
    message: string
  }
}

export function useCaeCli() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  const commandCandidates = [
    { name: 'cae-local-venv', label: 'E:\\cae-cli\\venv\\Scripts\\cae.exe' },
    { name: 'cae-project-venv', label: 'venv\\Scripts\\cae.exe' },
    { name: 'cae-path', label: 'cae' },
  ]
  const projectRoot = 'E:\\cae-cli'

  function parseOutput<T>(stdout: string): T {
    try {
      return JSON.parse(stdout) as T
    } catch {
      return stdout as unknown as T
    }
  }

  async function runCommand<T = unknown>(args: string[]): Promise<CommandResult<T>> {
    loading.value = true
    error.value = null

    try {
      const { Command } = await import('@tauri-apps/plugin-shell')
      const errors: string[] = []

      for (const candidate of commandCandidates) {
        try {
          const command = Command.create(candidate.name, args, { cwd: projectRoot })
          const output = await command.execute()
          const data = output.stdout ? parseOutput<T>(output.stdout) : undefined

          if (output.code !== 0) {
            const errMsg = output.stderr || `命令执行失败 (code: ${output.code})`
            error.value = errMsg
            return { ok: false, data, error: { code: 'EXEC_FAILED', message: errMsg } }
          }

          return { ok: true, data }
        } catch (e) {
          errors.push(`${candidate.label}: ${e instanceof Error ? e.message : String(e)}`)
        }
      }

      const errMsg = errors.join('\n')
      error.value = errMsg
      return { ok: false, error: { code: 'CALL_FAILED', message: errMsg } }
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : String(e)
      error.value = errMsg
      return { ok: false, error: { code: 'CALL_FAILED', message: errMsg } }
    } finally {
      loading.value = false
    }
  }

  async function solve(inputFile: string, outputDir?: string) {
    const args = ['solve', inputFile]
    if (outputDir) args.push('-o', outputDir)
    return runCommand(args)
  }

  async function diagnose(resultDir: string, options?: { ai?: boolean; json?: boolean }) {
    const args = ['diagnose', resultDir]
    if (options?.ai) args.push('--ai')
    if (options?.json) args.push('--json')
    return runCommand(args)
  }

  async function dockerStatus() {
    return runCommand(['docker', 'status'])
  }

  async function dockerCatalog() {
    return runCommand(['docker', 'catalog'])
  }

  async function dockerPull(image: string) {
    return runCommand(['docker', 'pull', image])
  }

  async function dockerCalculix(inputFile: string, image?: string, outputDir?: string) {
    const args = ['docker', 'calculix', inputFile]
    if (image) args.push('--image', image)
    if (outputDir) args.push('-o', outputDir)
    return runCommand(args)
  }

  async function inpCheck(file: string, options?: { json?: boolean }) {
    const args = ['inp', 'check', file]
    if (options?.json) args.push('--json')
    return runCommand(args)
  }

  async function inpInfo(file: string) {
    return runCommand(['inp', 'info', file])
  }

  async function solvers() {
    return runCommand(['solvers'])
  }

  async function info() {
    return runCommand(['info'])
  }

  async function guiSnapshot(projectRoot = 'E:\\cae-cli', inpFile?: string) {
    const args = ['gui', 'snapshot', '--project-root', projectRoot, '--json']
    if (inpFile) args.push('--inp', inpFile)
    return runCommand(args)
  }

  async function modelSet(modelName: string) {
    return runCommand(['model', 'set', modelName])
  }

  async function pickInpFile(startDir = projectRoot): Promise<string | null> {
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      return await invoke<string | null>('pick_inp_file', { startDir })
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : String(e)
      error.value = errMsg
      return null
    }
  }

  return {
    loading,
    error,
    runCommand,
    solve,
    diagnose,
    dockerStatus,
    dockerCatalog,
    dockerPull,
    dockerCalculix,
    inpCheck,
    inpInfo,
    solvers,
    info,
    guiSnapshot,
    modelSet,
    pickInpFile,
  }
}
