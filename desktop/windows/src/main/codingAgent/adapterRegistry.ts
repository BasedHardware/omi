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
  codex: 'OMI_CODEX_ADAPTER_COMMAND'
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
