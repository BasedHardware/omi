// The built-in launch command for each external coding agent — the ONLY command
// lines a renderer request can install without a native approval dialog. Main
// (ipc/codingAgent.ts) treats this map as the allowlist for `codingAgent:
// setCommands`; Settings → Agents reads the same map for its one-click Connect,
// so the suggestion the UI offers and the value main accepts can never drift.

import type { CodingAgentId } from './types'

export type ExternalCodingAgentId = Exclude<CodingAgentId, 'acp'>

export const SUGGESTED_AGENT_COMMANDS = {
  openclaw: 'openclaw acp',
  hermes: 'hermes acp',
  codex: 'npx -y @agentclientprotocol/codex-acp'
} as const satisfies Record<ExternalCodingAgentId, string>
