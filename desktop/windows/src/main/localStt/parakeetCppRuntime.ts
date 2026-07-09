import { spawn } from 'child_process'
import { createWriteStream } from 'fs'
import { access, mkdir, readdir, rename, rm } from 'fs/promises'
import { homedir, tmpdir } from 'os'
import { basename, dirname, join } from 'path'
import { Readable } from 'stream'
import { pipeline } from 'stream/promises'
import type { LocalSttStatus } from '../../shared/types'

export const PARAKEET_CPP_VERSION = 'v0.3.2'
export const PARAKEET_CPP_MODEL_NAME = 'tdt_ctc-110m-q8_0.gguf'
export const PARAKEET_CPP_MODEL_URL =
  'https://huggingface.co/mudler/parakeet-cpp-gguf/resolve/main/tdt_ctc-110m-q8_0.gguf'

const NVIDIA_TIMEOUT_MS = 1200
const INSTALL_TIMEOUT_MS = 10 * 60_000
const EXE_NAME = 'parakeet-cli.exe'

type RuntimeVariant = 'cuda' | 'cpu'
type RuntimeInstallState = LocalSttStatus['runtime']['installState']

export type ManagedParakeetRuntime = {
  exePath: string
  modelPath: string
  runtimeRoot: string
  variant: RuntimeVariant
  model: string
  version: string
}

type RuntimeDeps = {
  env?: NodeJS.ProcessEnv
  platform?: NodeJS.Platform | string
  arch?: string
  detectNvidiaGpu?: () => Promise<boolean | null>
  downloadFile?: (url: string, destination: string) => Promise<void>
  extractZip?: (zipPath: string, destination: string) => Promise<void>
  now?: () => number
  rootDir?: string
}

type RuntimeSelection = {
  supported: boolean
  reason?: string
  nvidiaAvailable: boolean | null
  variant: RuntimeVariant | null
  runtimeRoot: string
  binDir: string
  modelDir: string
  model: string
  modelUrl: string
  version: string
  releaseBase: string
}

let installPromise: Promise<ManagedParakeetRuntime> | null = null
let installState: RuntimeInstallState | null = null
let installError: string | null = null
let activeSessions = 0

export function managedParakeetModelName(env: NodeJS.ProcessEnv = process.env): string {
  return env.OMI_LOCAL_STT_MODEL_NAME || PARAKEET_CPP_MODEL_NAME
}

export function resetManagedParakeetRuntimeStateForTests(): void {
  installPromise = null
  installState = null
  installError = null
  activeSessions = 0
}

export function noteManagedParakeetSessionStarted(): void {
  activeSessions += 1
  if (installState === 'installed') installState = 'running'
}

export function noteManagedParakeetSessionStopped(): void {
  activeSessions = Math.max(0, activeSessions - 1)
  if (activeSessions === 0 && installState === 'running') installState = 'installed'
}

export async function detectNvidiaGpu(
  env: NodeJS.ProcessEnv = process.env
): Promise<boolean | null> {
  if (env.OMI_LOCAL_STT_ASSUME_NVIDIA === '1') return true

  return new Promise((resolve) => {
    const child = spawn('nvidia-smi', ['-L'], { windowsHide: true })
    let output = ''
    const timer = setTimeout(() => {
      try {
        child.kill()
      } catch {
        /* ignore */
      }
      resolve(null)
    }, NVIDIA_TIMEOUT_MS)
    timer.unref?.()

    child.stdout.on('data', (data) => {
      output += data.toString()
    })
    child.on('error', () => {
      clearTimeout(timer)
      resolve(null)
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      resolve(code === 0 && /GPU/i.test(output))
    })
  })
}

export async function getManagedParakeetStatus(deps: RuntimeDeps = {}): Promise<LocalSttStatus> {
  const now = deps.now ?? Date.now
  const checkedAt = now()
  const selection = await selectRuntime(deps)

  if (!selection.supported) {
    return {
      backend: 'parakeet',
      healthy: false,
      available: false,
      nvidiaAvailable: selection.nvidiaAvailable,
      managed: true,
      runtime: {
        kind: 'parakeet.cpp',
        installState: 'unsupported',
        variant: selection.variant,
        model: selection.model,
        canInstall: false
      },
      reason: selection.reason,
      checkedAt
    }
  }

  const runtime = await resolveInstalledRuntime(selection)
  const installed = runtime != null
  const state = runtimeInstallState(installed)

  return {
    backend: 'parakeet',
    healthy: installed,
    available: installed,
    nvidiaAvailable: selection.nvidiaAvailable,
    managed: true,
    runtime: {
      kind: 'parakeet.cpp',
      installState: state,
      variant: selection.variant,
      model: selection.model,
      canInstall: true
    },
    reason: runtimeStatusReason(state),
    checkedAt
  }
}

export type EnsureRuntimeOptions = {
  /**
   * When false, resolve an already-installed runtime but never download or
   * install anything — reject instead. Only an explicit Local Parakeet
   * selection may install; 'auto' must fail closed to the hosted cloud path.
   */
  allowInstall?: boolean
}

export async function ensureManagedParakeetRuntime(
  deps: RuntimeDeps = {},
  options: EnsureRuntimeOptions = {}
): Promise<ManagedParakeetRuntime> {
  if (installPromise) return installPromise
  installPromise = installManagedRuntime(deps, options.allowInstall ?? true).finally(() => {
    installPromise = null
  })
  return installPromise
}

async function installManagedRuntime(
  deps: RuntimeDeps,
  allowInstall: boolean
): Promise<ManagedParakeetRuntime> {
  const selection = await selectRuntime(deps)
  if (!selection.supported || !selection.variant) {
    throw new Error(selection.reason ?? 'local Parakeet runtime is not supported')
  }

  const existing = await resolveInstalledRuntime(selection)
  if (existing) {
    installError = null
    installState = activeSessions > 0 ? 'running' : 'installed'
    return existing
  }

  if (!allowInstall) {
    // Fail closed without touching installState: nothing was attempted, so the
    // status should keep reporting 'not_installed', not an install error.
    throw new Error(
      'local Parakeet runtime is not installed; select Local Parakeet in Settings to install it'
    )
  }

  installState = 'installing'
  installError = null

  try {
    await mkdir(selection.binDir, { recursive: true })
    await mkdir(selection.modelDir, { recursive: true })

    const artifacts = runtimeArtifacts(selection)
    const archiveDir = join(selection.runtimeRoot, 'archives')
    await mkdir(archiveDir, { recursive: true })

    for (const artifact of artifacts) {
      const archivePath = join(archiveDir, basename(new URL(artifact.url).pathname))
      await ensureDownloaded(artifact.url, archivePath, deps.downloadFile)
      await extractArchive(archivePath, selection.binDir, deps.extractZip)
    }

    const exePath = await findParakeetCli(selection.binDir)
    if (!exePath) throw new Error('installed Parakeet runtime did not include parakeet-cli.exe')

    const modelPath = join(selection.modelDir, selection.model)
    await ensureDownloaded(selection.modelUrl, modelPath, deps.downloadFile)

    const runtime = {
      exePath,
      modelPath,
      runtimeRoot: selection.runtimeRoot,
      variant: selection.variant,
      model: selection.model,
      version: selection.version
    } satisfies ManagedParakeetRuntime

    installState = activeSessions > 0 ? 'running' : 'installed'
    return runtime
  } catch (err) {
    installError = err instanceof Error ? err.message : String(err)
    installState = 'error'
    throw err
  }
}

async function selectRuntime(deps: RuntimeDeps): Promise<RuntimeSelection> {
  const env = deps.env ?? process.env
  const platform = deps.platform ?? process.platform
  const arch = deps.arch ?? process.arch
  const version = env.OMI_LOCAL_STT_PARAKEET_CPP_VERSION || PARAKEET_CPP_VERSION
  const model = managedParakeetModelName(env)
  const releaseBase =
    env.OMI_LOCAL_STT_RELEASE_BASE ||
    `https://github.com/mudler/parakeet.cpp/releases/download/${version}`
  const runtimeRoot = deps.rootDir ?? defaultRuntimeRoot(env, platform, version)
  const modelDir = join(runtimeRoot, 'models')
  const binDir = join(runtimeRoot, 'bin')
  const modelUrl = env.OMI_LOCAL_STT_MODEL_URL || PARAKEET_CPP_MODEL_URL
  const allowNonWindows = env.OMI_LOCAL_STT_ALLOW_NON_WINDOWS === '1'

  if (platform !== 'win32' && !allowNonWindows) {
    return {
      supported: false,
      reason: 'Local Parakeet install is only available in the Windows app',
      nvidiaAvailable: null,
      variant: null,
      runtimeRoot,
      binDir,
      modelDir,
      model,
      modelUrl,
      version,
      releaseBase
    }
  }

  if (arch !== 'x64' && arch !== 'amd64') {
    return {
      supported: false,
      reason: 'Local Parakeet install requires Windows x64',
      nvidiaAvailable: null,
      variant: null,
      runtimeRoot,
      binDir,
      modelDir,
      model,
      modelUrl,
      version,
      releaseBase
    }
  }

  const nvidiaAvailable =
    deps.detectNvidiaGpu != null ? await deps.detectNvidiaGpu() : await detectNvidiaGpu(env)
  const forcedVariant = env.OMI_LOCAL_STT_RUNTIME_VARIANT
  const allowNonNvidia = env.OMI_LOCAL_STT_ALLOW_NON_NVIDIA === '1'

  if (forcedVariant === 'cpu') {
    return {
      supported: true,
      nvidiaAvailable,
      variant: 'cpu',
      runtimeRoot,
      binDir,
      modelDir,
      model,
      modelUrl,
      version,
      releaseBase
    }
  }

  if (forcedVariant === 'cuda') {
    return {
      supported: true,
      nvidiaAvailable,
      variant: 'cuda',
      runtimeRoot,
      binDir,
      modelDir,
      model,
      modelUrl,
      version,
      releaseBase
    }
  }

  if (nvidiaAvailable === true) {
    return {
      supported: true,
      nvidiaAvailable,
      variant: 'cuda',
      runtimeRoot,
      binDir,
      modelDir,
      model,
      modelUrl,
      version,
      releaseBase
    }
  }

  if (allowNonNvidia) {
    return {
      supported: true,
      nvidiaAvailable,
      variant: 'cpu',
      runtimeRoot,
      binDir,
      modelDir,
      model,
      modelUrl,
      version,
      releaseBase
    }
  }

  return {
    supported: false,
    reason: 'NVIDIA GPU not detected',
    nvidiaAvailable,
    variant: null,
    runtimeRoot,
    binDir,
    modelDir,
    model,
    modelUrl,
    version,
    releaseBase
  }
}

function defaultRuntimeRoot(
  env: NodeJS.ProcessEnv,
  platform: NodeJS.Platform | string,
  version: string
): string {
  if (env.OMI_LOCAL_STT_RUNTIME_ROOT) return env.OMI_LOCAL_STT_RUNTIME_ROOT
  if (platform === 'win32') {
    const localAppData = env.LOCALAPPDATA || join(homedir(), 'AppData', 'Local')
    return join(localAppData, 'Omi for Windows', 'LocalSTT', 'parakeet.cpp', version)
  }
  return join(tmpdir(), 'omi-windows-local-stt', 'parakeet.cpp', version)
}

function runtimeArtifacts(selection: RuntimeSelection): { url: string }[] {
  if (selection.variant === 'cpu') {
    return [{ url: `${selection.releaseBase}/parakeet-${selection.version}-bin-win-cpu-x64.zip` }]
  }
  return [
    { url: `${selection.releaseBase}/parakeet-${selection.version}-bin-win-cuda-x64.zip` },
    { url: `${selection.releaseBase}/cudart-parakeet-bin-win-cuda-x64.zip` }
  ]
}

async function resolveInstalledRuntime(
  selection: RuntimeSelection
): Promise<ManagedParakeetRuntime | null> {
  if (!selection.supported || !selection.variant) return null
  const exePath = await findParakeetCli(selection.binDir)
  if (!exePath) return null
  const modelPath = join(selection.modelDir, selection.model)
  if (!(await fileExists(modelPath))) return null
  return {
    exePath,
    modelPath,
    runtimeRoot: selection.runtimeRoot,
    variant: selection.variant,
    model: selection.model,
    version: selection.version
  }
}

function runtimeInstallState(installed: boolean): RuntimeInstallState {
  if (installPromise) return 'installing'
  if (installed) return activeSessions > 0 ? 'running' : 'installed'
  if (installState === 'error') return 'error'
  return 'not_installed'
}

function runtimeStatusReason(state: RuntimeInstallState): string | undefined {
  if (state === 'installed' || state === 'running') return undefined
  if (state === 'installing') return 'Installing local Parakeet runtime'
  if (state === 'error') return installError ?? 'Local Parakeet install failed'
  return 'Local Parakeet will install on first use'
}

async function ensureDownloaded(
  url: string,
  destination: string,
  downloadFile = downloadFileDefault
): Promise<void> {
  if (await fileExists(destination)) return
  await mkdir(dirname(destination), { recursive: true })
  await downloadFile(url, destination)
}

async function downloadFileDefault(url: string, destination: string): Promise<void> {
  const part = `${destination}.part`
  await rm(part, { force: true })
  const response = await fetch(url)
  if (!response.ok || !response.body) {
    throw new Error(`failed to download Parakeet runtime asset (${response.status})`)
  }

  try {
    await pipeline(
      Readable.fromWeb(response.body as Parameters<typeof Readable.fromWeb>[0]),
      createWriteStream(part)
    )
    await rename(part, destination)
  } catch (err) {
    await rm(part, { force: true })
    throw err
  }
}

async function extractArchive(
  zipPath: string,
  destination: string,
  extractZip = extractZipDefault
): Promise<void> {
  await mkdir(destination, { recursive: true })
  await extractZip(zipPath, destination)
}

async function extractZipDefault(zipPath: string, destination: string): Promise<void> {
  await runProcess(
    'powershell.exe',
    [
      '-NoProfile',
      '-ExecutionPolicy',
      'Bypass',
      '-Command',
      'Expand-Archive -LiteralPath $args[0] -DestinationPath $args[1] -Force',
      zipPath,
      destination
    ],
    INSTALL_TIMEOUT_MS
  )
}

async function findParakeetCli(root: string, depth = 0): Promise<string | null> {
  if (depth > 5) return null
  let entries: Array<{ name: string; isFile: () => boolean; isDirectory: () => boolean }>
  try {
    entries = await readdir(root, { withFileTypes: true })
  } catch {
    return null
  }

  for (const entry of entries) {
    const fullPath = join(root, entry.name)
    if (entry.isFile() && entry.name.toLowerCase() === EXE_NAME) return fullPath
  }

  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const found = await findParakeetCli(join(root, entry.name), depth + 1)
    if (found) return found
  }
  return null
}

async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path)
    return true
  } catch {
    return false
  }
}

async function runProcess(command: string, args: string[], timeoutMs: number): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const child = spawn(command, args, { windowsHide: true })
    let stderr = ''
    const timer = setTimeout(() => {
      try {
        child.kill()
      } catch {
        /* ignore */
      }
      reject(new Error(`${command} timed out`))
    }, timeoutMs)
    timer.unref?.()

    child.stderr.on('data', (data) => {
      stderr += data.toString()
    })
    child.on('error', (err) => {
      clearTimeout(timer)
      reject(err)
    })
    child.on('close', (code) => {
      clearTimeout(timer)
      if (code === 0) {
        resolve()
        return
      }
      reject(new Error(stderr.trim() || `${command} exited with code ${code ?? 'unknown'}`))
    })
  })
}
