// Config-write MCP connectors that target a local CLI (Codex, OpenClaw, Hermes).
// Each is GATED behind a presence check: if the tool's CLI/config is not on this
// machine, the row shows "requires <tool>" and we NEVER shell out. Detection is a
// PATH / config-file probe (no process spawn); the connect action runs the tool's
// own MCP-registration command via execFile (arg array — never a shell string, so
// nothing here is interpolated into a shell).
//
// Codex is fully wired (the brief's exact command). OpenClaw and Hermes are
// detection-gated but their config-write is not yet ported (needs the exact
// macOS syntax); until then a detected-but-unported tool reports `available:false`
// so the UI shows a non-actionable "setup coming" state rather than a dead button.

import { execFile } from 'child_process'
import { homedir } from 'os'
import { join } from 'path'
import { promisify } from 'util'
import { MCP_SERVER_KEY, mcpServerUrl } from '../../shared/mcpExports'
import { commandOnPath, fileExists } from './cliPresence'

const run = promisify(execFile)

/** A CLI connector we can detect (and, for some, write config for). */
export type CliConnectorId = 'codex' | 'openclaw' | 'hermes'

export interface CliConnectorProbe {
  /** Present on this machine (CLI on PATH or its config exists). */
  detected: boolean
  /** We can actually write this tool's MCP config (Codex only, for now). */
  writable: boolean
}

/** Detect a CLI connector without spawning it. */
export function probeCliConnector(id: CliConnectorId, home = homedir()): CliConnectorProbe {
  switch (id) {
    case 'codex':
      return { detected: commandOnPath('codex'), writable: true }
    case 'openclaw':
      return { detected: commandOnPath('openclaw'), writable: false }
    case 'hermes':
      return {
        detected: commandOnPath('hermes') || fileExists(join(home, '.hermes', 'config.yaml')),
        writable: false
      }
  }
}

/**
 * Register Omi's hosted MCP server with Codex:
 *   codex mcp add omi-memory -- npx -y mcp-remote <url> --header "Authorization: Bearer <key>"
 * Codex owns idempotency (re-adding the same name replaces it). Args are passed
 * as an array to execFile — the key never touches a shell. Throws on non-zero exit.
 */
export async function connectCodex(apiBase: string, key: string): Promise<void> {
  const url = mcpServerUrl(apiBase)
  await run('codex', [
    'mcp',
    'add',
    MCP_SERVER_KEY,
    '--',
    'npx',
    '-y',
    'mcp-remote',
    url,
    '--header',
    `Authorization: Bearer ${key}`
  ])
}

/** Remove Omi's MCP server from Codex. Best-effort (no-op if already absent). */
export async function disconnectCodex(): Promise<void> {
  try {
    await run('codex', ['mcp', 'remove', MCP_SERVER_KEY])
  } catch {
    /* already gone / codex not present */
  }
}

/** True when Codex lists an omi-memory MCP server. */
export async function codexConnected(): Promise<boolean> {
  try {
    const { stdout } = await run('codex', ['mcp', 'list'])
    return stdout.includes(MCP_SERVER_KEY)
  } catch {
    return false
  }
}
