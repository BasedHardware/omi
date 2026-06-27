import type { LocalSttStatus } from '../../shared/types'
import {
  detectNvidiaGpu,
  getManagedParakeetStatus,
  managedParakeetModelName,
  type ManagedParakeetRuntime
} from './parakeetCppRuntime'

type StatusDeps = {
  env?: NodeJS.ProcessEnv
  platform?: NodeJS.Platform | string
  arch?: string
  detectNvidiaGpu?: () => Promise<boolean | null>
  downloadFile?: (url: string, destination: string) => Promise<void>
  extractZip?: (zipPath: string, destination: string) => Promise<void>
  now?: () => number
  rootDir?: string
}

export { detectNvidiaGpu }

export async function getLocalSttStatus(deps: StatusDeps = {}): Promise<LocalSttStatus> {
  const env = deps.env ?? process.env
  const now = deps.now ?? Date.now
  const checkedAt = now()

  if (env.OMI_FORCE_CLOUD_STT === '1' || env.OMI_LOCAL_STT_DISABLED === '1') {
    return disabledStatus('local STT disabled', env, checkedAt)
  }

  if (env.OMI_FORCE_PARAKEET_FAIL === '1') {
    return disabledStatus('forced local Parakeet failure', env, checkedAt)
  }

  return getManagedParakeetStatus(deps)
}

function disabledStatus(reason: string, env: NodeJS.ProcessEnv, checkedAt: number): LocalSttStatus {
  return {
    backend: 'parakeet',
    healthy: false,
    available: false,
    nvidiaAvailable: null,
    managed: true,
    runtime: {
      kind: 'parakeet.cpp',
      installState: 'unsupported',
      variant: null,
      model: managedParakeetModelName(env),
      canInstall: false
    },
    reason,
    checkedAt
  }
}

export type { ManagedParakeetRuntime }
