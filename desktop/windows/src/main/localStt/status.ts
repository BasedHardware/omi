import { spawn } from 'child_process'
import type { LocalSttStatus } from '../../shared/types'

const DEFAULT_PARAKEET_URL = 'http://127.0.0.1:8765'
const HEALTH_TIMEOUT_MS = 1000
const NVIDIA_TIMEOUT_MS = 1200

type StatusDeps = {
  env?: NodeJS.ProcessEnv
  platform?: NodeJS.Platform | string
  fetchImpl?: typeof fetch
  detectNvidiaGpu?: () => Promise<boolean | null>
  now?: () => number
}

export function localParakeetBaseUrl(env: NodeJS.ProcessEnv = process.env): string {
  return (env.OMI_LOCAL_PARAKEET_URL || env.OMI_PARAKEET_URL || DEFAULT_PARAKEET_URL).replace(
    /\/+$/,
    ''
  )
}

function timeoutSignal(ms: number): AbortSignal {
  const controller = new AbortController()
  setTimeout(() => controller.abort(), ms).unref?.()
  return controller.signal
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

export async function getLocalSttStatus(deps: StatusDeps = {}): Promise<LocalSttStatus> {
  const env = deps.env ?? process.env
  const platform = deps.platform ?? process.platform
  const fetchImpl = deps.fetchImpl ?? fetch
  const now = deps.now ?? Date.now
  const configuredUrl = localParakeetBaseUrl(env)
  const healthUrl = `${configuredUrl}/health`
  const checkedAt = now()

  if (env.OMI_FORCE_CLOUD_STT === '1' || env.OMI_LOCAL_STT_DISABLED === '1') {
    return {
      backend: 'parakeet',
      configuredUrl,
      healthUrl,
      healthy: false,
      available: false,
      nvidiaAvailable: null,
      reason: 'local STT disabled',
      checkedAt
    }
  }

  if (env.OMI_FORCE_PARAKEET_FAIL === '1') {
    return {
      backend: 'parakeet',
      configuredUrl,
      healthUrl,
      healthy: false,
      available: false,
      nvidiaAvailable: null,
      reason: 'forced local Parakeet failure',
      checkedAt
    }
  }

  let healthy = false
  try {
    const response = await fetchImpl(healthUrl, { signal: timeoutSignal(HEALTH_TIMEOUT_MS) })
    healthy = response.ok
  } catch {
    healthy = false
  }

  if (!healthy) {
    return {
      backend: 'parakeet',
      configuredUrl,
      healthUrl,
      healthy: false,
      available: false,
      nvidiaAvailable: null,
      reason: `Parakeet runtime is not healthy at ${configuredUrl}`,
      checkedAt
    }
  }

  const nvidiaAvailable =
    deps.detectNvidiaGpu != null ? await deps.detectNvidiaGpu() : await detectNvidiaGpu(env)
  const allowNonNvidia = env.OMI_LOCAL_STT_ALLOW_NON_NVIDIA === '1'
  const needsNvidia = platform === 'win32'

  if (needsNvidia && !allowNonNvidia && nvidiaAvailable !== true) {
    return {
      backend: 'parakeet',
      configuredUrl,
      healthUrl,
      healthy: true,
      available: false,
      nvidiaAvailable,
      reason: 'NVIDIA GPU not detected',
      checkedAt
    }
  }

  return {
    backend: 'parakeet',
    configuredUrl,
    healthUrl,
    healthy: true,
    available: true,
    nvidiaAvailable,
    checkedAt
  }
}
