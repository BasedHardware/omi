// Claude Code MCP config-write. Claude Code reads a single JSON file at
// ~/.claude.json (same path on Windows — %USERPROFILE%\.claude.json). We add one
// `mcpServers["omi-memory"]` HTTP entry pointing at Omi's hosted MCP SSE endpoint,
// authenticated by the hosted MCP key.
//
// SAFETY (never corrupt an existing config):
//   • parse-modify-write — read the whole file, preserve every unknown key,
//     touch only mcpServers["omi-memory"].
//   • if the file exists but is unparseable, we DO NOT write (that would clobber a
//     real config); the caller surfaces an error instead.
//   • back up before every content-changing write (newest 5 kept).
//   • idempotent — if the entry already matches, no backup, no write.
//   • verify-after-write — re-read and confirm the entry landed.
//
// The hosted key is a credential: it lives inside this file's headers, so nothing
// here is ever logged.

import { existsSync, readFileSync, writeFileSync, copyFileSync, readdirSync, rmSync } from 'fs'
import { homedir } from 'os'
import { join, basename, dirname } from 'path'
import {
  MCP_SERVER_KEY,
  buildHttpServerEntry,
  mcpServerUrl,
  type McpHttpServerEntry
} from '../../shared/mcpExports'
import { fileExists, dirExists, commandOnPath } from './cliPresence'

const MAX_BACKUPS = 5

// Monotonic tie-breaker so two backups taken in the same millisecond get
// distinct, chronologically-sortable filenames (rapid key rotations).
let backupSeq = 0

/** ~/.claude.json — the Claude Code config path (identical layout on Windows). */
export function claudeConfigPath(home = homedir()): string {
  return join(home, '.claude.json')
}

/**
 * Is Claude Code present on this machine? True when its config or config dir
 * exists, or the `claude` CLI is on PATH. Absent → the row shows
 * "Claude Code not detected" and offers no write.
 */
export function detectClaudeCode(home = homedir()): boolean {
  return (
    fileExists(claudeConfigPath(home)) ||
    dirExists(join(home, '.claude')) ||
    commandOnPath('claude')
  )
}

/** A shape that tolerates any prior config content while we edit one key. */
type ClaudeConfig = { mcpServers?: Record<string, unknown> } & Record<string, unknown>

class CorruptConfigError extends Error {
  constructor() {
    super('Existing Claude config is not valid JSON; refusing to overwrite it')
    this.name = 'CorruptConfigError'
  }
}

/** Read + parse the config. Missing → {}. Present-but-corrupt → throws (never clobber). */
function readConfig(path: string): ClaudeConfig {
  if (!existsSync(path)) return {}
  const text = readFileSync(path, 'utf8')
  if (text.trim() === '') return {}
  try {
    const parsed = JSON.parse(text) as unknown
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed as ClaudeConfig
    throw new CorruptConfigError()
  } catch (e) {
    if (e instanceof CorruptConfigError) throw e
    throw new CorruptConfigError()
  }
}

/** True when the existing entry already equals the target (structural compare). */
function entryMatches(existing: unknown, target: McpHttpServerEntry): boolean {
  if (!existing || typeof existing !== 'object') return false
  const e = existing as Record<string, unknown>
  const headers = e.headers as Record<string, unknown> | undefined
  return (
    e.type === target.type &&
    e.url === target.url &&
    !!headers &&
    headers.Authorization === target.headers.Authorization
  )
}

/** Copy the config aside before a changing write, pruning to the newest MAX_BACKUPS. */
function backupConfig(path: string): void {
  if (!existsSync(path)) return
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  const seq = String(backupSeq++).padStart(6, '0')
  copyFileSync(path, `${path}.omi-backup-${stamp}-${seq}`)
  pruneBackups(path)
}

function pruneBackups(path: string): void {
  const dir = dirname(path)
  const prefix = `${basename(path)}.omi-backup-`
  try {
    const backups = readdirSync(dir)
      .filter((n) => n.startsWith(prefix))
      .sort() // ISO-ish timestamps sort chronologically
    for (const stale of backups.slice(0, Math.max(0, backups.length - MAX_BACKUPS))) {
      rmSync(join(dir, stale), { force: true })
    }
  } catch {
    /* best-effort */
  }
}

export interface ClaudeWriteResult {
  /** False when the entry already matched (no backup, no write). */
  changed: boolean
  configPath: string
}

/**
 * Idempotently write the omi-memory MCP entry into ~/.claude.json.
 * @throws CorruptConfigError if the existing file is present but not valid JSON.
 * @throws if the post-write verification read does not match.
 */
export function writeClaudeMcpEntry(
  apiBase: string,
  key: string,
  path = claudeConfigPath()
): ClaudeWriteResult {
  const target = buildHttpServerEntry(mcpServerUrl(apiBase), key)
  const config = readConfig(path)
  const servers = (config.mcpServers ?? {}) as Record<string, unknown>

  if (entryMatches(servers[MCP_SERVER_KEY], target)) {
    return { changed: false, configPath: path }
  }

  backupConfig(path)
  const next: ClaudeConfig = {
    ...config,
    mcpServers: { ...servers, [MCP_SERVER_KEY]: target }
  }
  writeFileSync(path, `${JSON.stringify(next, null, 2)}\n`, 'utf8')

  // Verify-after-write: re-read and confirm the entry landed intact.
  const verify = readConfig(path)
  const wrote = (verify.mcpServers ?? {})[MCP_SERVER_KEY]
  if (!entryMatches(wrote, target)) {
    throw new Error('Claude config write verification failed')
  }
  return { changed: true, configPath: path }
}

/** True when ~/.claude.json already has an omi-memory entry for `apiBase`. */
export function claudeMcpConnected(apiBase: string, path = claudeConfigPath()): boolean {
  try {
    const servers = (readConfig(path).mcpServers ?? {}) as Record<string, unknown>
    const entry = servers[MCP_SERVER_KEY] as { url?: unknown } | undefined
    return entry?.url === mcpServerUrl(apiBase)
  } catch {
    return false
  }
}

/** Remove the omi-memory entry (disconnect). Backs up first; no-op if absent. */
export function removeClaudeMcpEntry(path = claudeConfigPath()): boolean {
  let config: ClaudeConfig
  try {
    config = readConfig(path)
  } catch {
    return false // corrupt — don't touch
  }
  const servers = (config.mcpServers ?? {}) as Record<string, unknown>
  if (!(MCP_SERVER_KEY in servers)) return false
  backupConfig(path)
  const nextServers = { ...servers }
  delete nextServers[MCP_SERVER_KEY]
  writeFileSync(path, `${JSON.stringify({ ...config, mcpServers: nextServers }, null, 2)}\n`, 'utf8')
  return true
}

export { CorruptConfigError }
