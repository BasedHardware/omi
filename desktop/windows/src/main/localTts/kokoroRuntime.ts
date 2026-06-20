import { access, mkdir, readdir, rm } from 'fs/promises'
import { homedir, tmpdir } from 'os'
import { join } from 'path'
import { pathToFileURL } from 'url'
import { randomUUID } from 'crypto'
import type {
  LocalTtsStatus,
  LocalTtsSynthesizeRequest,
  LocalTtsSynthesizeResult
} from '../../shared/types'

export const KOKORO_MODEL_ID = 'onnx-community/Kokoro-82M-v1.0-ONNX'
export const KOKORO_DEFAULT_VOICE = 'af_heart'

const MAX_TTS_CHARS = 4000
const AUDIO_RETENTION_MS = 24 * 60 * 60 * 1000

type KokoroInstallState = LocalTtsStatus['runtime']['installState']
type KokoroDtype = 'fp32' | 'fp16' | 'q8' | 'q4' | 'q4f16'

type RawAudioLike = {
  save: (filePath: string) => Promise<void> | void
}

type KokoroTtsLike = {
  generate: (text: string, options?: { voice?: string; speed?: number }) => Promise<RawAudioLike>
}

type KokoroModuleLike = {
  KokoroTTS: {
    from_pretrained: (
      modelId: string,
      options?: {
        dtype?: KokoroDtype
        device?: 'cpu' | 'wasm' | 'webgpu' | null
        progress_callback?: (progress: unknown) => void
      }
    ) => Promise<KokoroTtsLike>
  }
}

type TransformersModuleLike = {
  env: {
    cacheDir: string
    allowRemoteModels: boolean
    allowLocalModels: boolean
    useFSCache: boolean
  }
}

type RuntimeSelection = {
  supported: boolean
  reason?: string
  runtimeRoot: string
  modelCacheDir: string
  audioDir: string
  model: string
  voice: string
  dtype: KokoroDtype
}

type RuntimeDeps = {
  env?: NodeJS.ProcessEnv
  platform?: NodeJS.Platform | string
  arch?: string
  now?: () => number
  rootDir?: string
  loadKokoro?: () => Promise<KokoroModuleLike>
  loadTransformers?: () => Promise<TransformersModuleLike>
}

let loadPromise: Promise<KokoroTtsLike> | null = null
let kokoroTts: KokoroTtsLike | null = null
let installState: KokoroInstallState | null = null
let installError: string | null = null
let activeSyntheses = 0
let lastCleanupAt = 0

export function resetManagedKokoroRuntimeStateForTests(): void {
  loadPromise = null
  kokoroTts = null
  installState = null
  installError = null
  activeSyntheses = 0
  lastCleanupAt = 0
}

export async function getManagedKokoroStatus(deps: RuntimeDeps = {}): Promise<LocalTtsStatus> {
  const now = deps.now ?? Date.now
  const checkedAt = now()
  const selection = selectRuntime(deps)

  if (!selection.supported) {
    return statusFromSelection(selection, 'unsupported', false, checkedAt, selection.reason)
  }

  const installed = await hasModelCache(selection.modelCacheDir)
  const loaded = kokoroTts != null
  const state = runtimeInstallState(installed || loaded)

  return statusFromSelection(
    selection,
    state,
    installed || loaded,
    checkedAt,
    runtimeStatusReason(state)
  )
}

export async function synthesizeWithManagedKokoro(
  request: LocalTtsSynthesizeRequest,
  deps: RuntimeDeps = {}
): Promise<LocalTtsSynthesizeResult> {
  const text = normalizeText(request.text)
  if (!text) throw new Error('Text is required for local TTS')

  const selection = selectRuntime(deps)
  if (!selection.supported) {
    throw new Error(selection.reason ?? 'local Kokoro TTS is not supported')
  }

  const tts = await ensureManagedKokoroRuntime(deps, selection)
  const voice = normalizeVoice(request.voice, selection.voice)
  const speed = normalizeSpeed(request.speed)
  const audioDir = selection.audioDir
  await mkdir(audioDir, { recursive: true })
  await cleanupOldAudio(audioDir, deps.now ?? Date.now).catch(() => {
    /* best effort */
  })

  const audioPath = join(audioDir, `kokoro-${Date.now()}-${randomUUID()}.wav`)
  activeSyntheses += 1
  installState = 'running'
  try {
    const audio = await tts.generate(text, { voice, speed })
    await audio.save(audioPath)
    return {
      audioPath,
      audioUrl: pathToFileURL(audioPath).toString(),
      mimeType: 'audio/wav'
    }
  } catch (err) {
    installError = err instanceof Error ? err.message : String(err)
    installState = 'error'
    throw err
  } finally {
    activeSyntheses = Math.max(0, activeSyntheses - 1)
    if (installState === 'running' && activeSyntheses === 0) installState = 'installed'
  }
}

async function ensureManagedKokoroRuntime(
  deps: RuntimeDeps,
  selection = selectRuntime(deps)
): Promise<KokoroTtsLike> {
  if (kokoroTts) return kokoroTts
  if (loadPromise) return loadPromise
  loadPromise = loadManagedRuntime(deps, selection).finally(() => {
    loadPromise = null
  })
  return loadPromise
}

async function loadManagedRuntime(
  deps: RuntimeDeps,
  selection: RuntimeSelection
): Promise<KokoroTtsLike> {
  if (!selection.supported) {
    throw new Error(selection.reason ?? 'local Kokoro TTS is not supported')
  }
  installState = 'installing'
  installError = null

  try {
    await mkdir(selection.runtimeRoot, { recursive: true })
    await mkdir(selection.modelCacheDir, { recursive: true })

    const transformers = await loadTransformersModule(deps)
    transformers.env.cacheDir = selection.modelCacheDir
    transformers.env.allowRemoteModels = true
    transformers.env.allowLocalModels = true
    transformers.env.useFSCache = true

    const kokoro = await loadKokoroModule(deps)
    const runtime = await kokoro.KokoroTTS.from_pretrained(selection.model, {
      dtype: selection.dtype,
      device: 'cpu'
    })
    kokoroTts = runtime
    installState = 'installed'
    return runtime
  } catch (err) {
    installError = err instanceof Error ? err.message : String(err)
    installState = 'error'
    throw err
  }
}

function selectRuntime(deps: RuntimeDeps): RuntimeSelection {
  const env = deps.env ?? process.env
  const platform = deps.platform ?? process.platform
  const arch = deps.arch ?? process.arch
  const model = env.OMI_LOCAL_TTS_MODEL_ID || KOKORO_MODEL_ID
  const voice = env.OMI_LOCAL_TTS_VOICE || KOKORO_DEFAULT_VOICE
  const dtype = normalizeDtype(env.OMI_LOCAL_TTS_DTYPE)
  const runtimeRoot = deps.rootDir ?? defaultRuntimeRoot(env, platform)
  const modelCacheDir = join(runtimeRoot, 'models')
  const audioDir = join(runtimeRoot, 'audio')
  const allowNonWindows = env.OMI_LOCAL_TTS_ALLOW_NON_WINDOWS === '1'

  if (env.OMI_LOCAL_TTS_DISABLED === '1') {
    return unsupported(
      'local TTS disabled',
      runtimeRoot,
      modelCacheDir,
      audioDir,
      model,
      voice,
      dtype
    )
  }

  if (platform !== 'win32' && !allowNonWindows) {
    return unsupported(
      'Local Kokoro TTS is only available in the Windows app',
      runtimeRoot,
      modelCacheDir,
      audioDir,
      model,
      voice,
      dtype
    )
  }

  if (arch !== 'x64' && arch !== 'amd64') {
    return unsupported(
      'Local Kokoro TTS requires Windows x64',
      runtimeRoot,
      modelCacheDir,
      audioDir,
      model,
      voice,
      dtype
    )
  }

  return { supported: true, runtimeRoot, modelCacheDir, audioDir, model, voice, dtype }
}

function unsupported(
  reason: string,
  runtimeRoot: string,
  modelCacheDir: string,
  audioDir: string,
  model: string,
  voice: string,
  dtype: KokoroDtype
): RuntimeSelection {
  return { supported: false, reason, runtimeRoot, modelCacheDir, audioDir, model, voice, dtype }
}

function defaultRuntimeRoot(env: NodeJS.ProcessEnv, platform: NodeJS.Platform | string): string {
  if (env.OMI_LOCAL_TTS_RUNTIME_ROOT) return env.OMI_LOCAL_TTS_RUNTIME_ROOT
  if (platform === 'win32') {
    const localAppData = env.LOCALAPPDATA || join(homedir(), 'AppData', 'Local')
    return join(localAppData, 'Omi for Windows', 'LocalTTS', 'kokoro-js')
  }
  return join(tmpdir(), 'omi-windows-local-tts', 'kokoro-js')
}

function statusFromSelection(
  selection: RuntimeSelection,
  installState: KokoroInstallState,
  available: boolean,
  checkedAt: number,
  reason?: string
): LocalTtsStatus {
  return {
    backend: 'kokoro',
    healthy: available,
    available,
    managed: true,
    runtime: {
      kind: 'kokoro-js',
      installState,
      model: selection.model,
      voice: selection.voice,
      canInstall: selection.supported
    },
    reason,
    checkedAt
  }
}

function runtimeInstallState(installed: boolean): KokoroInstallState {
  if (loadPromise) return 'installing'
  if (activeSyntheses > 0) return 'running'
  if (installed) return 'installed'
  if (installState === 'error') return 'error'
  return 'not_installed'
}

function runtimeStatusReason(state: KokoroInstallState): string | undefined {
  if (state === 'installed' || state === 'running') return undefined
  if (state === 'installing') return 'Installing local Kokoro TTS'
  if (state === 'error') return installError ?? 'Local Kokoro TTS failed'
  return 'Local Kokoro TTS will install on first spoken reply'
}

function normalizeText(text: string): string {
  return text.replace(/\s+/g, ' ').trim().slice(0, MAX_TTS_CHARS)
}

function normalizeVoice(voice: string | undefined, fallback: string): string {
  const trimmed = voice?.trim()
  return trimmed && /^[a-z]{2}_[a-z0-9_-]+$/i.test(trimmed) ? trimmed : fallback
}

function normalizeSpeed(speed: number | undefined): number {
  if (typeof speed !== 'number' || !Number.isFinite(speed)) return 1
  return Math.min(2, Math.max(0.5, speed))
}

function normalizeDtype(value: string | undefined): KokoroDtype {
  if (
    value === 'fp32' ||
    value === 'fp16' ||
    value === 'q8' ||
    value === 'q4' ||
    value === 'q4f16'
  ) {
    return value
  }
  return 'q8'
}

async function hasModelCache(modelCacheDir: string): Promise<boolean> {
  try {
    const entries = await readdir(modelCacheDir, { recursive: true, withFileTypes: true })
    return entries.some((entry) => entry.isFile())
  } catch {
    return false
  }
}

async function cleanupOldAudio(audioDir: string, now: () => number): Promise<void> {
  const current = now()
  if (current - lastCleanupAt < 60 * 60 * 1000) return
  lastCleanupAt = current
  const entries = await readdir(audioDir, { withFileTypes: true }).catch(() => [])
  await Promise.all(
    entries
      .filter((entry) => entry.isFile() && entry.name.endsWith('.wav'))
      .map(async (entry) => {
        const fullPath = join(audioDir, entry.name)
        const match = /^kokoro-(\d+)-/.exec(entry.name)
        const createdAt = match ? Number(match[1]) : current
        if (current - createdAt > AUDIO_RETENTION_MS && (await exists(fullPath))) {
          await rm(fullPath, { force: true })
        }
      })
  )
}

async function exists(path: string): Promise<boolean> {
  try {
    await access(path)
    return true
  } catch {
    return false
  }
}

async function loadKokoroModule(deps: RuntimeDeps): Promise<KokoroModuleLike> {
  if (deps.loadKokoro) return deps.loadKokoro()
  return import('kokoro-js') as Promise<KokoroModuleLike>
}

async function loadTransformersModule(deps: RuntimeDeps): Promise<TransformersModuleLike> {
  if (deps.loadTransformers) return deps.loadTransformers()
  return import('@huggingface/transformers') as Promise<TransformersModuleLike>
}
