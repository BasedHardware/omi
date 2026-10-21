// Config-write MCP connectors that target a local CLI (Codex, OpenClaw, Hermes),
// ported from macOS MemoryBankConnector.swift. Each is CLI-GATED: if the tool is
// not present, the row shows "requires <tool>" and we never touch it. When it IS
// present, "Connect" writes the tool's NATIVE MCP config — Codex and Hermes both
// speak Streamable HTTP directly, so no mcp-remote bridge is used. If a write
// FAILS, the caller falls back to showing the manual copy-config card.
//
//   • Codex   — ~/.codex/config.toml `[mcp_servers.omi-memory]` url + http_headers
//   • OpenClaw— `openclaw mcp set omi-memory '<json>'` + `openclaw mcp reload` + SOUL.md note
//   • Hermes  — ~/.hermes/config.yaml `mcp_servers.omi-memory` url + headers + SOUL.md note
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
import {
  MCP_SERVER_KEY,
  mcpServerUrl,
  mcpLegacyServerUrl,
  type McpSetupCard
} from '../../shared/mcpExports'
import { commandOnPath, fileExists } from './cliPresence'
import { atomicWriteFileSync } from './atomicWrite'
import {
  argsBearerScans,
  argsEndpoint,
  bearerToken,
  entryConnection,
  jsonEntryScan,
  stringArrayValue,
  type EntryConnection,
  type OwnedEntryScan
} from './entryScan'

const execFileAsync = promisify(execFile)
const CLI_TIMEOUT_MS = 20_000
const SOUL_MARKER = 'omi-memory-bank'

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
      // The writer is file-native, so an existing config counts as present too.
      return { detected: commandOnPath('codex') || fileExists(codexConfigPath(home)) }
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

/** How the owned config entry relates to the canonical endpoint + key. */
export type CliConnection = EntryConnection

/** A TOML double-quoted basic string is JSON-compatible; a single-quoted
 *  literal is `'…'` verbatim. Anything else (bare value, number, trailing
 *  junk that isn't a comment) is not a scalar we can trust. */
function tomlScalar(raw: string): string | null {
  const m = raw.trim().match(/^("(?:[^"\\]|\\.)*"|'[^']*')/)
  if (!m) return null
  const rest = raw.trim().slice(m[1].length).trim()
  if (rest !== '' && !rest.startsWith('#')) return null
  if (m[1].startsWith("'")) return m[1].slice(1, -1)
  try {
    const v: unknown = JSON.parse(m[1])
    return typeof v === 'string' ? v : null
  } catch {
    return null
  }
}

/** A YAML scalar after `key:` — quoted like a TOML scalar, or a bare value
 *  trimmed at a ` #` comment. An empty value is a mapping opener, not a URL. */
function yamlScalar(raw: string): string | null {
  const v = raw.trim()
  if (v.startsWith('"') || v.startsWith("'")) return tomlScalar(v)
  const hash = v.indexOf(' #')
  const bare = (hash >= 0 ? v.slice(0, hash) : v).trimEnd()
  return bare === '' ? null : bare
}

/** Parse `url`, `args`, and `http_headers` out of the owned Codex section's
 *  `key = value` lines (each value is single-line — the section scan already
 *  refused anything else). */
function codexOwnedEntry(lines: string[]): OwnedEntryScan {
  const endpoints: (string | null)[] = []
  const bearers: (string | null)[] = []
  for (const raw of lines) {
    const kv = raw.trim().match(/^([A-Za-z0-9_-]+)\s*=\s*(.+)$/)
    if (!kv) continue
    const [, field, value] = kv
    if (field === 'url') {
      endpoints.push(tomlScalar(value))
    } else if (field === 'args') {
      const args = stringArrayValue(value)
      if (args) {
        endpoints.push(...argsEndpoint(args))
        bearers.push(...argsBearerScans(args))
      } else {
        endpoints.push(null)
      }
    } else if (field === 'http_headers' || field === 'headers') {
      const auth = value.match(/Authorization\s*=\s*("(?:[^"\\]|\\.)*"|'[^']*')/)
      if (auth) {
        const s = tomlScalar(auth[1])
        bearers.push(s === null ? null : bearerToken(s))
      }
    }
  }
  return { endpoints, bearers }
}

/** Parse the owned Hermes sub-block: direct-child `url:`/`args:` fields plus
 *  the `Authorization:` header line (which sits one level deeper). */
function hermesOwnedEntry(lines: string[]): OwnedEntryScan {
  const endpoints: (string | null)[] = []
  const bearers: (string | null)[] = []
  for (const raw of lines) {
    const child = raw.match(/^ {4}([A-Za-z0-9_-]+)\s*:\s*(.*)$/)
    if (child) {
      const [, field, value] = child
      if (field === 'url') endpoints.push(yamlScalar(value))
      else if (field === 'args') {
        const args = stringArrayValue(value)
        if (args) {
          endpoints.push(...argsEndpoint(args))
          bearers.push(...argsBearerScans(args))
        } else {
          endpoints.push(null)
        }
      }
    }
    const auth = raw.match(/^\s+Authorization\s*:\s*(.*)$/)
    if (auth) {
      const s = yamlScalar(auth[1])
      bearers.push(s === null ? null : bearerToken(s))
    }
  }
  return { endpoints, bearers }
}

export function cliConnectionState(
  id: CliConnectorId,
  apiBase: string,
  key: string,
  home = homedir()
): CliConnection {
  const url = mcpServerUrl(apiBase)
  const legacyUrl = mcpLegacyServerUrl(apiBase)
  try {
    switch (id) {
      case 'codex': {
        const p = codexConfigPath(home)
        if (!existsSync(p)) return 'disconnected'
        const lines = readFileSync(p, 'utf8').split('\n')
        // Same authoritative parser as the writer — an ambiguous/malformed or
        // commented-out section can never read as connected.
        const section = codexOwnedSection(lines)
        if (!section) return 'disconnected'
        return entryConnection(
          codexOwnedEntry(lines.slice(section.start, section.end)),
          url,
          legacyUrl,
          key
        )
      }
      case 'openclaw': {
        const p = join(home, '.openclaw', 'openclaw.json')
        if (!existsSync(p)) return 'disconnected'
        const json = JSON.parse(readFileSync(p, 'utf8')) as {
          mcp?: { servers?: Record<string, unknown> }
        }
        const server = json.mcp?.servers?.[MCP_SERVER_KEY]
        if (!server) return 'disconnected'
        return entryConnection(jsonEntryScan(server), url, legacyUrl, key)
      }
      case 'hermes': {
        const p = join(home, '.hermes', 'config.yaml')
        if (!existsSync(p)) return 'disconnected'
        // Only the owned mcp_servers → omi-memory block counts.
        const owned = hermesOwnedBlock(readFileSync(p, 'utf8'))
        return owned === null
          ? 'disconnected'
          : entryConnection(hermesOwnedEntry(owned.split('\n')), url, legacyUrl, key)
      }
    }
  } catch {
    return 'disconnected'
  }
}

export function cliConnected(
  id: CliConnectorId,
  apiBase: string,
  key: string,
  home = homedir()
): boolean {
  return cliConnectionState(id, apiBase, key, home) === 'connected'
}

// --- setup cards (manual fallback) ------------------------------------------

export function buildSetupCard(id: CliConnectorId, apiBase: string, key: string): McpSetupCard {
  const url = mcpServerUrl(apiBase)
  switch (id) {
    case 'codex':
      return {
        copyTitle: 'Copy config',
        copyText: codexBlock(url, key),
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
        copyText: hermesBlock(url, key),
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
  switch (id) {
    case 'codex':
      // Native config write — `codex mcp add --url` could also register HTTP, but
      // writing the file directly needs no CLI and survives malformed-file
      // checks the CLI would skip.
      upsertCodexConfig(codexConfigPath(home), url, key)
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

export async function disconnectCli(id: CliConnectorId, home = homedir()): Promise<void> {
  try {
    if (id === 'codex') removeCodexMcpEntry(codexConfigPath(home))
    else if (id === 'openclaw') await run('openclaw', ['mcp', 'remove', MCP_SERVER_KEY])
    // Hermes has no remove CLI; leaving the YAML entry is harmless (best-effort).
  } catch {
    /* already gone / tool absent */
  }
}

// --- helpers: Codex TOML / Hermes YAML writers + SOUL.md note ----------------

/** ~/.codex/config.toml — Codex's native MCP config path. */
export function codexConfigPath(home = homedir()): string {
  return join(home, '.codex', 'config.toml')
}

const CODEX_SECTION_HEADER = `[mcp_servers.${MCP_SERVER_KEY}]`
const CODEX_KEY_RE = '(?:omi-memory|"omi-memory"|\'omi-memory\')'
const CODEX_MCP_KEY_RE = '(?:mcp_servers|"mcp_servers"|\'mcp_servers\')'
const CODEX_SECTION_RE = new RegExp(`^\\s*\\[mcp_servers\\.${CODEX_KEY_RE}\\]\\s*$`)
const CODEX_SUBTABLE_RE = new RegExp(`^\\s*\\[mcp_servers\\.${CODEX_KEY_RE}\\.[^\\]]+\\]\\s*$`)
const CODEX_PARENT_TABLE_RE = new RegExp(`^\\s*\\[${CODEX_MCP_KEY_RE}\\]\\s*(?:#.*)?$`)
const CODEX_ANY_TABLE_RE = /^\s*\[/
const CODEX_KV_RE = /^[A-Za-z0-9_.-]+\s*=/
// `omi-memory = {...}` (or `omi-memory.x = ...`) inside a bare [mcp_servers]
// table, and `mcp_servers.omi-memory(.x)? = ...` dotted keys in the document
// prologue, define the same entry through forms we can't rewrite — ambiguous.
const CODEX_INLINE_SERVER_RE = new RegExp(`^\\s*${CODEX_KEY_RE}(?:\\.|\\s*=)`)
const CODEX_DOTTED_SERVER_RE = new RegExp(`^\\s*${CODEX_MCP_KEY_RE}\\.${CODEX_KEY_RE}(?:\\.|\\s*=)`)

/**
 * The native Codex `[mcp_servers.omi-memory]` block: Streamable HTTP `url` plus
 * the Bearer header in an inline `http_headers` table (no mcp-remote bridge, no
 * bearer_token_env_var — a persistent external env isn't guaranteed). Values are
 * JSON.stringify'd, which is also valid TOML double-quoted escaping.
 */
function codexBlock(url: string, key: string): string {
  return [
    CODEX_SECTION_HEADER,
    `url = ${JSON.stringify(url)}`,
    `http_headers = { Authorization = ${JSON.stringify(`Bearer ${key}`)} }`
  ].join('\n')
}

/** [start, end) line range of the owned `[mcp_servers.omi-memory]` section —
 *  the authoritative parser for both the writer and the connected re-scan.
 *  `end` stops after the last `key = value` line, so comments/blanks sitting
 *  before the NEXT table stay untouched. Throws rather than overwriting when
 *  the owned table is ambiguous (duplicate or quoted-key alternative), has
 *  nested subtables we can't preserve, or contains an unparseable body line. */
function codexOwnedSection(lines: string[]): { start: number; end: number } | null {
  const starts: number[] = []
  let inAnyTable = false
  let inServersParent = false
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i]
    if (CODEX_SECTION_RE.test(l)) {
      starts.push(i)
      inAnyTable = true
      inServersParent = false
    } else if (CODEX_SUBTABLE_RE.test(l)) {
      throw new Error(
        `${CODEX_SECTION_HEADER} has a nested subtable we can't preserve; refusing to edit`
      )
    } else if (CODEX_PARENT_TABLE_RE.test(l)) {
      inAnyTable = true
      inServersParent = true
    } else if (CODEX_ANY_TABLE_RE.test(l)) {
      inAnyTable = true
      inServersParent = false
    } else if (inServersParent && CODEX_INLINE_SERVER_RE.test(l)) {
      throw new Error(`${CODEX_SECTION_HEADER} is ambiguous; refusing to edit`)
    } else if (!inAnyTable && CODEX_DOTTED_SERVER_RE.test(l)) {
      throw new Error(`${CODEX_SECTION_HEADER} is ambiguous; refusing to edit`)
    }
  }
  if (starts.length === 0) return null
  if (starts.length > 1 || !/^\s*\[mcp_servers\.omi-memory\]/.test(lines[starts[0]])) {
    throw new Error(`${CODEX_SECTION_HEADER} is ambiguous; refusing to edit`)
  }
  let lastKv = -1
  for (let i = starts[0] + 1; i < lines.length && !/^\s*\[/.test(lines[i]); i++) {
    const l = lines[i].trim()
    if (l === '' || l.startsWith('#')) continue
    if (!CODEX_KV_RE.test(l)) {
      throw new Error(`${CODEX_SECTION_HEADER} contains a line we can't parse; refusing to edit`)
    }
    lastKv = i
  }
  return { start: starts[0], end: lastKv < 0 ? starts[0] + 1 : lastKv + 1 }
}

/**
 * Idempotently upsert the native Codex MCP entry in ~/.codex/config.toml,
 * preserving every other section. @throws on a malformed or ambiguous owned section.
 */
export function upsertCodexConfig(path: string, url: string, key: string): void {
  const block = codexBlock(url, key)
  const text = existsSync(path) ? readFileSync(path, 'utf8') : ''
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 })
  const section = codexOwnedSection(text.split('\n'))
  if (!section) {
    const sep = text.length && !text.endsWith('\n') ? '\n' : ''
    atomicWriteFileSync(path, `${text}${sep}${block}\n`, 0o600)
    return
  }
  const lines = text.split('\n')
  lines.splice(section.start, section.end - section.start, block)
  // The owned-section scan can consume the phantom '' from a trailing newline;
  // re-terminate so identical upserts are byte-for-byte stable.
  const out = lines.join('\n')
  atomicWriteFileSync(path, out.endsWith('\n') ? out : `${out}\n`, 0o600)
}

/** Remove the owned `[mcp_servers.omi-memory]` section; no-op when absent. */
export function removeCodexMcpEntry(path: string): boolean {
  if (!existsSync(path)) return false
  const text = readFileSync(path, 'utf8')
  const lines = text.split('\n')
  const section = codexOwnedSection(lines)
  if (!section) return false
  lines.splice(section.start, section.end - section.start)
  const out = lines.join('\n')
  atomicWriteFileSync(path, out.endsWith('\n') ? out : `${out}\n`, 0o600)
  return true
}

/**
 * The native Hermes `mcp_servers` sub-block (verified against Hermes' own docs):
 * a Streamable HTTP `url` plus a `headers` map — no npx/mcp-remote bridge.
 * Values are double-quoted YAML scalars (JSON.stringify escaping is valid YAML).
 */
function hermesBlock(url: string, key: string): string {
  return [
    `  ${MCP_SERVER_KEY}:`,
    `    url: ${JSON.stringify(url)}`,
    `    headers:`,
    `      Authorization: ${JSON.stringify(`Bearer ${key}`)}`
  ].join('\n')
}

/**
 * Locate the top-level `mcp_servers:` mapping and its line range
 * [topIdx, endIdx) — endIdx is the first line after it that starts another
 * top-level key (comments/blanks don't end a mapping). Throws on a duplicate
 * `mcp_servers` key or a non-empty inline mapping we can't safely rewrite;
 * `mcp_servers: {}` reports `inlineEmpty` so the caller converts it to a block.
 */
function hermesServersSection(lines: string[]): {
  topIdx: number
  endIdx: number
  inlineEmpty: boolean
} | null {
  const tops: number[] = []
  for (let i = 0; i < lines.length; i++) {
    if (/^mcp_servers:/.test(lines[i])) tops.push(i)
  }
  if (tops.length === 0) return null
  if (tops.length > 1) throw new Error('duplicate mcp_servers mappings; refusing to edit')
  const topIdx = tops[0]
  const rest = lines[topIdx].slice('mcp_servers:'.length).trim()
  const block = rest === '' || rest.startsWith('#')
  const inlineEmpty = rest === '{}' || rest.startsWith('{} ')
  if (!block && !inlineEmpty) {
    throw new Error('mcp_servers is a non-empty inline mapping; refusing to overwrite')
  }
  let endIdx = topIdx + 1
  while (endIdx < lines.length) {
    const l = lines[endIdx]
    const indented = l.startsWith(' ') || l.startsWith('\t')
    if (l.trim() !== '' && !indented && !l.trimStart().startsWith('#')) break
    endIdx++
  }
  // The block writer only emits the 2-space convention. A mapping written with
  // a different child indent (4-space, tab) is refused rather than edited into
  // a mixed-indentation invalid document.
  let minIndent = Number.POSITIVE_INFINITY
  for (let i = topIdx + 1; i < endIdx; i++) {
    const l = lines[i]
    if (l.trim() === '' || l.trimStart().startsWith('#')) continue
    const spaces = l.match(/^ */)?.[0].length ?? 0
    if (l[spaces] === '\t') {
      minIndent = 0
      break
    }
    minIndent = Math.min(minIndent, spaces)
  }
  if (minIndent !== Number.POSITIVE_INFINITY && minIndent !== 2) {
    throw new Error('mcp_servers uses non-two-space indentation; refusing to edit')
  }
  return { topIdx, endIdx, inlineEmpty }
}

/** [startIdx, endIdx) range of the owned `  omi-memory:` sub-block inside the
 *  top-level mcp_servers mapping (null when absent). Bounded to that section,
 *  so a same-named key under another top-level key can never match. */
function hermesOwnedRange(lines: string[]): { startIdx: number; endIdx: number } | null {
  const section = hermesServersSection(lines)
  if (!section || section.inlineEmpty) return null
  const startIdx = lines.findIndex(
    (l, i) => i > section.topIdx && i < section.endIdx && l.startsWith(`  ${MCP_SERVER_KEY}:`)
  )
  if (startIdx < 0) return null
  let endIdx = startIdx + 1
  while (
    endIdx < lines.length &&
    (lines[endIdx].startsWith('    ') || lines[endIdx].trim() === '')
  ) {
    endIdx++
  }
  return { startIdx, endIdx }
}

/** Slice out the owned `mcp_servers` → `omi-memory` block (null when absent). */
function hermesOwnedBlock(text: string): string | null {
  const lines = text.split('\n')
  const range = hermesOwnedRange(lines)
  return range ? lines.slice(range.startIdx, range.endIdx).join('\n') : null
}

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
  const block = hermesBlock(url, key)

  const text = existsSync(path) ? readFileSync(path, 'utf8') : ''
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 })

  const lines = text.split('\n')
  const section = hermesServersSection(lines)
  if (!section) {
    const sep = text.length && !text.endsWith('\n') ? '\n' : ''
    atomicWriteFileSync(path, `${text}${sep}mcp_servers:\n${block}\n`, 0o600)
    return
  }

  if (section.inlineEmpty) {
    // `mcp_servers: {}` — convert the empty inline mapping to a block.
    lines.splice(section.topIdx, 1, 'mcp_servers:', block)
  } else {
    const owned = hermesOwnedRange(lines)
    if (!owned) {
      // Append at the end of the mcp_servers section, before the next top key.
      let insertIdx = section.endIdx
      while (insertIdx > section.topIdx + 1 && lines[insertIdx - 1].trim() === '') insertIdx--
      lines.splice(insertIdx, 0, block)
    } else {
      lines.splice(owned.startIdx, owned.endIdx - owned.startIdx, block)
    }
  }
  // Re-terminate: the scan may consume the phantom '' from a trailing newline.
  const out = lines.join('\n')
  atomicWriteFileSync(path, out.endsWith('\n') ? out : `${out}\n`, 0o600)
}
