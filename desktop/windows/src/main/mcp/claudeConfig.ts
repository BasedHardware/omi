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

import { existsSync, readFileSync, copyFileSync, readdirSync, rmSync, mkdirSync } from 'fs'
import { homedir } from 'os'
import { randomUUID } from 'crypto'
import { join, dirname } from 'path'
import { atomicWriteFileSync } from './atomicWrite'
import {
  MCP_SERVER_KEY,
  buildHttpServerEntry,
  mcpServerUrl,
  type McpHttpServerEntry
} from '../../shared/mcpExports'
import { fileExists, commandOnPath } from './cliPresence'

const MAX_BACKUPS = 5

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
    fileExists(join(home, '.claude', 'settings.json')) ||
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
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed))
      return parsed as ClaudeConfig
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

// Backups live under ~/.claude/backups/ named .claude.json.backup.<epochMs>-<uuid>
// (Mac parity). epochMs sorts chronologically; the uuid makes same-ms rotations
// distinct. Pruned to the newest MAX_BACKUPS.
const BACKUP_PREFIX = '.claude.json.backup.'

function backupDir(path: string): string {
  return join(dirname(path), '.claude', 'backups')
}

/** Copy the config aside before a changing write, pruning to the newest MAX_BACKUPS. */
function backupConfig(path: string): void {
  if (!existsSync(path)) return
  const dir = backupDir(path)
  mkdirSync(dir, { recursive: true })
  copyFileSync(path, join(dir, `${BACKUP_PREFIX}${Date.now()}-${randomUUID()}`))
  pruneBackups(path)
}

function pruneBackups(path: string): void {
  const dir = backupDir(path)
  try {
    const backups = readdirSync(dir)
      .filter((n) => n.startsWith(BACKUP_PREFIX))
      .sort() // epochMs prefix sorts chronologically
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
  atomicWriteFileSync(path, `${JSON.stringify(next, null, 2)}\n`)

  // Verify-after-write: re-read and confirm the entry landed intact.
  const verify = readConfig(path)
  const wrote = (verify.mcpServers ?? {})[MCP_SERVER_KEY]
  if (!entryMatches(wrote, target)) {
    throw new Error('Claude config write verification failed')
  }
  return { changed: true, configPath: path }
}

/**
 * True when ~/.claude.json has an omi-memory entry whose URL matches `apiBase`.
 * When `key` is given, ALSO require the entry's Bearer to equal it — so a
 * rotated/stale key reads as disconnected (Mac's key-aware re-scan). Omit `key`
 * to test only that an entry exists (used to decide whether to rewrite on rotate).
 */
export function claudeMcpConnected(
  apiBase: string,
  path = claudeConfigPath(),
  key?: string
): boolean {
  try {
    const servers = (readConfig(path).mcpServers ?? {}) as Record<string, unknown>
    const entry = servers[MCP_SERVER_KEY] as
      | { url?: unknown; headers?: { Authorization?: unknown } }
      | undefined
    if (entry?.url !== mcpServerUrl(apiBase)) return false
    if (key === undefined) return true
    return entry.headers?.Authorization === `Bearer ${key}`
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
  atomicWriteFileSync(path, `${JSON.stringify({ ...config, mcpServers: nextServers }, null, 2)}\n`)
  return true
}

export { CorruptConfigError }
