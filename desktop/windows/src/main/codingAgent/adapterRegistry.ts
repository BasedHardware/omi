// Static adapter profile registry — trimmed Windows port of macOS's
// adapter-selection.ts. Claude Code ("acp") is always activated; the three
// external adapters activate when a command is configured, either via a stored
// app preference (settings UI writes these) or the matching env var (power
// users / parity with macOS). No worker pools or live-instance registry: the
// task layer creates an adapter per task via `createAdapter`.

import { ClaudeCodeRuntimeAdapter } from './claudeCode'
import { OpenClawRuntimeAdapter } from './openclaw'
import { HermesRuntimeAdapter } from './hermes'
import { CodexRuntimeAdapter } from './codex'
import { PiMonoAdapter, PiMonoRuntimeAdapter } from './piMono'
import { getPiMonoByokEnv, getPiMonoSession, piMonoManagedApiBaseUrl } from './piMonoSession'
import {
  adapterCapabilitiesFor,
  type AdapterCapabilities,
  type ProductionAdapterId,
  type RuntimeAdapter
} from './interface'

export const ADAPTER_ACTIVATION_ENV = {
  acp: undefined, // Claude Code — bundled bridge, no install or env var needed
  openclaw: 'OMI_OPENCLAW_ADAPTER_COMMAND',
  hermes: 'OMI_HERMES_ADAPTER_COMMAND',
  codex: 'OMI_CODEX_ADAPTER_COMMAND',
  'pi-mono': undefined // managed-cloud default-chat engine — no install/env, token-gated
} as const satisfies Record<ProductionAdapterId, string | undefined>

export type ExternalAdapterId = Exclude<ProductionAdapterId, 'acp'>

/** Commands configured outside env vars (the settings UI persists these). */
export type AdapterCommandOverrides = Partial<Record<ExternalAdapterId, string>>

export interface AdapterProfile {
  adapterId: ProductionAdapterId
  displayName: string
  activationEnv?: string
  capabilities: AdapterCapabilities
  createAdapter: (options: { log: (message: string) => void; command?: string }) => RuntimeAdapter
}

export const ADAPTER_PROFILES: Record<ProductionAdapterId, AdapterProfile> = {
  acp: {
    adapterId: 'acp',
    displayName: 'Claude Code',
    activationEnv: ADAPTER_ACTIVATION_ENV.acp,
    capabilities: adapterCapabilitiesFor('acp'),
    createAdapter: ({ log }) => new ClaudeCodeRuntimeAdapter({ log })
  },
  openclaw: {
    adapterId: 'openclaw',
    displayName: 'OpenClaw',
    activationEnv: ADAPTER_ACTIVATION_ENV.openclaw,
    capabilities: adapterCapabilitiesFor('openclaw'),
    createAdapter: ({ log, command }) => new OpenClawRuntimeAdapter({ log, command })
  },
  hermes: {
    adapterId: 'hermes',
    displayName: 'Hermes',
    activationEnv: ADAPTER_ACTIVATION_ENV.hermes,
    capabilities: adapterCapabilitiesFor('hermes'),
    createAdapter: ({ log, command }) => new HermesRuntimeAdapter({ log, command })
  },
  codex: {
    adapterId: 'codex',
    displayName: 'Codex',
    activationEnv: ADAPTER_ACTIVATION_ENV.codex,
    capabilities: adapterCapabilitiesFor('codex'),
    createAdapter: ({ log, command }) => new CodexRuntimeAdapter({ log, command })
  },
  // pi-mono is the managed-cloud default-chat engine, present only to satisfy the
  // `Record<ProductionAdapterId, …>` totality (matrix membership forces it). It is
  // NOT a coding-agent pill/fallback — PRODUCTION_ADAPTER_IDS excludes it, so this
  // profile is never selected via the coding-agent task path. `createAdapter`
  // ignores `command` (pi-mono is bundled, not a user command) and builds from the
  // relayed Firebase session; it throws when signed out. The live kernel factory
  // that actually spawns pi-mono lives in agentKernel/controlPlane.ts.
  'pi-mono': {
    adapterId: 'pi-mono',
    displayName: 'Omi',
    activationEnv: ADAPTER_ACTIVATION_ENV['pi-mono'],
    capabilities: adapterCapabilitiesFor('pi-mono'),
    createAdapter: ({ log }) => {
      const session = getPiMonoSession()
      if (!session) {
        throw new Error('pi-mono requires a signed-in session (no Firebase token relayed yet).')
      }
      return new PiMonoRuntimeAdapter(
        new PiMonoAdapter({
          omiApiBaseUrl: piMonoManagedApiBaseUrl(session),
          authToken: session.token,
          byokEnv: getPiMonoByokEnv(),
          onRestart: (reason) => log(`[pi-mono] restart: ${reason}`)
        })
      )
    }
  }
}

/**
 * The command string that would be used to launch an external adapter, or
 * undefined when nothing is configured. Preference overrides win over env
 * vars so what the settings UI shows is what runs.
 */
export function adapterConfiguredCommand(
  adapterId: ProductionAdapterId,
  overrides: AdapterCommandOverrides = {},
  env: NodeJS.ProcessEnv = process.env
): string | undefined {
  const activationEnv = ADAPTER_PROFILES[adapterId].activationEnv
  if (activationEnv === undefined) return undefined
  const override = overrides[adapterId as ExternalAdapterId]?.trim()
  if (override) return override
  const fromEnv = env[activationEnv]?.trim()
  return fromEnv || undefined
}

// Whether a coding agent is usable. `pi-mono` returns `true` unconditionally via
// the `activationEnv === undefined` branch (like acp), but that value is never
// consumed on a coding-agent path: pi-mono is excluded from PRODUCTION_ADAPTER_IDS,
// so neither the pill list nor the delegated-task fallback (candidateAgents) ever
// calls this for it. pi-mono's real gate is the relayed Firebase session, enforced
// in the kernel registration factory (agentKernel/controlPlane.ts) and in this
// module's pi-mono `createAdapter`. No special-case needed here.
export function adapterIsActivated(
  adapterId: ProductionAdapterId,
  overrides: AdapterCommandOverrides = {},
  env: NodeJS.ProcessEnv = process.env
): boolean {
  if (ADAPTER_PROFILES[adapterId].activationEnv === undefined) return true
  return adapterConfiguredCommand(adapterId, overrides, env) !== undefined
}

export function adapterProfile(adapterId: ProductionAdapterId): AdapterProfile {
  return ADAPTER_PROFILES[adapterId]
}

/** User-facing hint shown when a named agent isn't connected yet. Rendered as
 *  markdown in chat, so the env var is backtick-escaped (bare underscores
 *  would be eaten as italics). */
export function adapterActivationError(adapterId: ProductionAdapterId): string | undefined {
  const profile = ADAPTER_PROFILES[adapterId]
  if (!profile.activationEnv) return undefined
  return `Install ${profile.displayName} first, then add its launch command in Settings → Agents (or set \`${profile.activationEnv}\`).`
}
