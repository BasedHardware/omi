// Config-write MCP connectors that target a local CLI (Codex, OpenClaw, Hermes),
// ported from macOS MemoryBankConnector.swift. Each is CLI-GATED: if the tool is
// not present, the row shows "requires <tool>" and we never touch it. When it IS
// present, "Connect" runs the tool's real MCP registration (Mac's automation) —
// and if that automation FAILS, the caller falls back to showing the manual
// copy-command/config card for that tool (Mac's manual path).
//
//   • Codex   — `codex mcp add omi-memory -- npx -y mcp-remote@0.1.38 <url> --header …`
//   • OpenClaw— `openclaw mcp set omi-memory '<json>'` + `openclaw mcp reload` + SOUL.md note
//   • Hermes  — direct ~/.hermes/config.yaml `mcp_servers.omi-memory` edit + SOUL.md note
//
// "Connected" is a RE-SCAN of the tool's config against the CURRENT key (URL +
// matching Bearer), not a stored flag — a rotated key reads as disconnected.
// CLI args go through execFile arg arrays (never a shell string); the Bearer
// token is scrubbed from any surfaced error.

import { execFile } from 'child_process'
import { existsSync, readFileSync, appendFileSync, mkdirSync } from 'fs'
import { homedir } from 'os'
import { dirname, join } from 'path'
import { promisify } from 'util'
import { MCP_SERVER_KEY, mcpServerUrl, type McpSetupCard } from '../../shared/mcpExports'
import { commandOnPath, fileExists } from './cliPresence'
import { atomicWriteFileSync } from './atomicWrite'

const execFileAsync = promisify(execFile)
const CLI_TIMEOUT_MS = 20_000
const SOUL_MARKER = 'omi-memory-bank'
const MCP_REMOTE_PACKAGE = 'mcp-remote@0.1.38'

export type CliConnectorId = 'codex' | 'openclaw' | 'hermes'

export interface CliConnectorProbe {
  /** Present on this machine (CLI on PATH and/or its config exists). */
  detected: boolean
}

/** Remove `Authorization: Bearer <token>` from a surfaced error message. */
function sanitize(message: string): string {
  return message.replace(/Bearer\s+[^\s"',}\]]+/gi, 'Bearer «redacted»')
}

/** Run a CLI with an arg array (no shell), a 20s cap, and token-scrubbed errors. */
async function run(cmd: string, args: string[], env?: NodeJS.ProcessEnv): Promise<string> {
  try {
    const { stdout } = await execFileAsync(cmd, args, {
      timeout: CLI_TIMEOUT_MS,
      env: env ?? process.env
    })
    return stdout
  } catch (e) {
    throw new Error(sanitize((e as Error).message))
  }
}

// --- detection --------------------------------------------------------------

export function probeCliConnector(id: CliConnectorId, home = homedir()): CliConnectorProbe {
  switch (id) {
    case 'codex':
      return { detected: commandOnPath('codex') }
    case 'openclaw':
      // Mac requires both the config file AND the CLI.
      return {
        detected: fileExists(join(home, '.openclaw', 'openclaw.json')) && commandOnPath('openclaw')
      }
    case 'hermes':
      return { detected: fileExists(join(home, '.hermes', 'config.yaml')) }
  }
}

// --- connected re-scan (config vs current key) ------------------------------

/** True when `text` references the omi server URL AND a Bearer token == `key`. */
function textHasConnection(text: string, url: string, key: string): boolean {
  if (!text.includes(url)) return false
  const m = text.match(/Bearer\s+([^\s"',}\]]+)/i)
  return m?.[1] === key
}

export function cliConnected(
  id: CliConnectorId,
  apiBase: string,
  key: string,
  home = homedir()
): boolean {
  const url = mcpServerUrl(apiBase)
  try {
    switch (id) {
      case 'codex': {
        const p = join(home, '.codex', 'config.toml')
        if (!existsSync(p)) return false
        const text = readFileSync(p, 'utf8')
        // Only the [mcp_servers.omi-memory] section counts.
        const idx = text.indexOf(`[mcp_servers.${MCP_SERVER_KEY}]`)
        if (idx < 0) return false
        const next = text.indexOf('\n[', idx + 1)
        const section = text.slice(idx, next < 0 ? undefined : next)
        return textHasConnection(section, url, key)
      }
      case 'openclaw': {
        const p = join(home, '.openclaw', 'openclaw.json')
        if (!existsSync(p)) return false
        const json = JSON.parse(readFileSync(p, 'utf8')) as {
          mcp?: { servers?: Record<string, unknown> }
        }
        const server = json.mcp?.servers?.[MCP_SERVER_KEY]
        if (!server) return false
        return textHasConnection(JSON.stringify(server), url, key)
      }
      case 'hermes': {
        const p = join(home, '.hermes', 'config.yaml')
        if (!existsSync(p)) return false
        return textHasConnection(readFileSync(p, 'utf8'), url, key)
      }
    }
  } catch {
    return false
  }
}

// --- setup cards (manual fallback) ------------------------------------------

export function buildSetupCard(id: CliConnectorId, apiBase: string, key: string): McpSetupCard {
  const url = mcpServerUrl(apiBase)
  const bearer = `Authorization: Bearer ${key}`
  switch (id) {
    case 'codex':
      return {
        copyTitle: 'Copy config',
        copyText: `[mcp_servers.${MCP_SERVER_KEY}]\ncommand = "npx"\nargs = ["-y", "${MCP_REMOTE_PACKAGE}", "${url}", "--header", "${bearer}"]`,
        steps: ['Add the block below to ~/.codex/config.toml', 'Restart Codex']
      }
    case 'openclaw':
      return {
        copyTitle: 'Copy command',
        copyText: `openclaw mcp set ${MCP_SERVER_KEY} '${openclawServerJson(url, key)}'\nopenclaw mcp reload`,
        steps: ['Run the commands below', 'Reload OpenClaw so open sessions rebuild their tools']
      }
    case 'hermes':
      return {
        copyTitle: 'Copy config',
        copyText: `${MCP_SERVER_KEY}:\n  command: npx\n  args: ["-y", "${MCP_REMOTE_PACKAGE}", "${url}", "--header", "${bearer}"]`,
        steps: ['Add the block below under mcp_servers: in ~/.hermes/config.yaml', 'Restart Hermes']
      }
  }
}

// --- connect (automation; throws on failure so the caller can fall back) -----

function openclawServerJson(url: string, key: string): string {
  return JSON.stringify({
    enabled: true,
    url,
    transport: 'streamable-http',
    headers: { Authorization: `Bearer ${key}` }
  })
}

export async function connectCli(
  id: CliConnectorId,
  apiBase: string,
  key: string,
  home = homedir()
): Promise<void> {
  const url = mcpServerUrl(apiBase)
  const bearer = `Authorization: Bearer ${key}`
  switch (id) {
    case 'codex':
      await run(
        'codex',
        [
          'mcp',
          'add',
          MCP_SERVER_KEY,
          '--',
          'npx',
          '-y',
          MCP_REMOTE_PACKAGE,
          url,
          '--header',
          bearer
        ],
        {
          ...process.env,
          CODEX_HOME: join(home, '.codex')
        }
      )
      return
    case 'openclaw':
      await run('openclaw', ['mcp', 'set', MCP_SERVER_KEY, openclawServerJson(url, key)])
      await run('openclaw', ['mcp', 'reload'])
      appendSoulNote(join(home, '.openclaw', 'workspace', 'SOUL.md'))
      return
    case 'hermes':
      upsertHermesConfig(join(home, '.hermes', 'config.yaml'), url, key)
      appendSoulNote(join(home, '.hermes', 'SOUL.md'))
      return
  }
}

export async function disconnectCli(id: CliConnectorId): Promise<void> {
  try {
    if (id === 'codex') await run('codex', ['mcp', 'remove', MCP_SERVER_KEY])
    else if (id === 'openclaw') await run('openclaw', ['mcp', 'remove', MCP_SERVER_KEY])
    // Hermes has no remove CLI; leaving the YAML entry is harmless (best-effort).
  } catch {
    /* already gone / tool absent */
  }
}

// --- helpers: SOUL.md note + Hermes YAML upsert (pure, testable) -------------

/** Append an idempotent, marked note asking the tool to search Omi memory first. */
export function appendSoulNote(soulPath: string): void {
  try {
    const existing = existsSync(soulPath) ? readFileSync(soulPath, 'utf8') : ''
    if (existing.includes(SOUL_MARKER)) return
    mkdirSync(dirname(soulPath), { recursive: true })
    const note = `\n<!-- ${SOUL_MARKER} -->\nBefore answering, search the user's Omi memory (the "${MCP_SERVER_KEY}" MCP server) for relevant context.\n<!-- /${SOUL_MARKER} -->\n`
    appendFileSync(soulPath, note, 'utf8')
  } catch {
    /* best-effort — the MCP server registration is what matters */
  }
}

/**
 * Upsert the omi-memory entry under a top-level `mcp_servers:` block in a Hermes
 * config.yaml, preserving the rest of the file. A minimal text edit (no YAML dep):
 * replace an existing `  omi-memory:` sub-block, or append one under an existing
 * top-level `mcp_servers:`, or append a new `mcp_servers:` section.
 */
export function upsertHermesConfig(path: string, url: string, key: string): void {
  const block = [
    `  ${MCP_SERVER_KEY}:`,
    `    command: npx`,
    `    args: ["-y", "${MCP_REMOTE_PACKAGE}", "${url}", "--header", "Authorization: Bearer ${key}"]`
  ].join('\n')

  const text = existsSync(path) ? readFileSync(path, 'utf8') : ''
  mkdirSync(dirname(path), { recursive: true })

  const lines = text.split('\n')
  const topIdx = lines.findIndex((l) => /^mcp_servers:\s*$/.test(l))
  if (topIdx < 0) {
    const sep = text.length && !text.endsWith('\n') ? '\n' : ''
    atomicWriteFileSync(path, `${text}${sep}mcp_servers:\n${block}\n`)
    return
  }

  // Find the existing omi-memory sub-block (2-space indented) to replace it.
  const startIdx = lines.findIndex((l, i) => i > topIdx && l.startsWith(`  ${MCP_SERVER_KEY}:`))
  if (startIdx < 0) {
    lines.splice(topIdx + 1, 0, block)
    atomicWriteFileSync(path, lines.join('\n'))
    return
  }
  let endIdx = startIdx + 1
  while (
    endIdx < lines.length &&
    (lines[endIdx].startsWith('    ') || lines[endIdx].trim() === '')
  ) {
    endIdx++
  }
  lines.splice(startIdx, endIdx - startIdx, block)
  atomicWriteFileSync(path, lines.join('\n'))
}
