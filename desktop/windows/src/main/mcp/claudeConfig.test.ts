import { describe, it, expect, beforeEach, afterAll } from 'vitest'
import {
  mkdtempSync,
  rmSync,
  writeFileSync,
  readFileSync,
  readdirSync,
  existsSync,
  mkdirSync
} from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import {
  writeClaudeMcpEntry,
  claudeMcpConnected,
  removeClaudeMcpEntry,
  claudeConfigPath,
  detectClaudeCode,
  CorruptConfigError
} from './claudeConfig'
import { MCP_SERVER_KEY, mcpServerUrl } from '../../shared/mcpExports'

const root = mkdtempSync(join(tmpdir(), 'claude-config-test-'))
afterAll(() => rmSync(root, { recursive: true, force: true }))

const API = 'https://api.omi.me'
const KEY = 'mcp_secret_abc'
// Each test gets its own directory so backup files never leak across cases.
let dir: string
let path: string
let n = 0

beforeEach(() => {
  dir = join(root, `t${n++}`)
  mkdirSync(dir, { recursive: true })
  path = join(dir, '.claude.json')
})

// The raw config read back for assertions. A permissive shape keeps the
// `.mcpServers[key].url` / sibling-key checks terse without per-access casts.
type McpEntry = {
  type?: string
  url?: string
  headers?: { Authorization?: string }
  command?: string
}
type ReadConfig = { mcpServers: Record<string, McpEntry> } & Record<string, unknown>
function read(): ReadConfig {
  return JSON.parse(readFileSync(path, 'utf8')) as ReadConfig
}

// Backups live under <home>/.claude/backups/ (Mac parity). `dir` is the fake home.
function backupsDir(): string {
  return join(dir, '.claude', 'backups')
}
function listBackups(): string[] {
  try {
    return readdirSync(backupsDir()).filter((f) => f.startsWith('.claude.json.backup.'))
  } catch {
    return []
  }
}
function backupCount(): number {
  return listBackups().length
}

describe('writeClaudeMcpEntry', () => {
  it('writes the omi-memory http entry into a fresh (missing) config', () => {
    const r = writeClaudeMcpEntry(API, KEY, path)
    expect(r.changed).toBe(true)
    const entry = read().mcpServers[MCP_SERVER_KEY]
    expect(entry).toEqual({
      type: 'http',
      url: mcpServerUrl(API),
      headers: { Authorization: `Bearer ${KEY}` }
    })
  })

  it('is idempotent — a second identical write makes no change and no backup', () => {
    writeClaudeMcpEntry(API, KEY, path)
    const backupsAfterFirst = backupCount()
    const r = writeClaudeMcpEntry(API, KEY, path)
    expect(r.changed).toBe(false)
    expect(backupCount()).toBe(backupsAfterFirst)
  })

  it('preserves unknown top-level keys AND sibling mcpServers entries', () => {
    writeFileSync(
      path,
      JSON.stringify({
        theme: 'dark',
        numStartups: 7,
        mcpServers: { other: { type: 'stdio', command: 'x' } }
      }),
      'utf8'
    )
    writeClaudeMcpEntry(API, KEY, path)
    const cfg = read()
    expect(cfg.theme).toBe('dark')
    expect(cfg.numStartups).toBe(7)
    expect(cfg.mcpServers.other).toEqual({ type: 'stdio', command: 'x' })
    expect(cfg.mcpServers[MCP_SERVER_KEY]?.url).toBe(mcpServerUrl(API))
  })

  it('backs up the prior config before a changing write', () => {
    writeFileSync(path, JSON.stringify({ theme: 'light' }), 'utf8')
    writeClaudeMcpEntry(API, KEY, path)
    const backups = listBackups()
    expect(backups.length).toBe(1)
    expect(JSON.parse(readFileSync(join(backupsDir(), backups[0]), 'utf8'))).toEqual({
      theme: 'light'
    })
  })

  it('keeps only the newest 5 backups', () => {
    writeFileSync(path, JSON.stringify({ v: 0 }), 'utf8')
    // Each changing write (rotating the key) makes one backup.
    for (let i = 1; i <= 8; i++) writeClaudeMcpEntry(API, `key-${i}`, path)
    expect(backupCount()).toBe(5)
  })

  it('REFUSES to overwrite a present-but-corrupt config (throws, no write)', () => {
    writeFileSync(path, '{ this is not json ', 'utf8')
    expect(() => writeClaudeMcpEntry(API, KEY, path)).toThrow(CorruptConfigError)
    // The corrupt file is left untouched — not clobbered.
    expect(readFileSync(path, 'utf8')).toBe('{ this is not json ')
  })

  it('updates the entry when the key rotates', () => {
    writeClaudeMcpEntry(API, 'old-key', path)
    const r = writeClaudeMcpEntry(API, 'new-key', path)
    expect(r.changed).toBe(true)
    expect(read().mcpServers[MCP_SERVER_KEY]?.headers?.Authorization).toBe('Bearer new-key')
  })
})

describe('claudeMcpConnected', () => {
  it('is true only when an entry for this apiBase exists', () => {
    expect(claudeMcpConnected(API, path)).toBe(false)
    writeClaudeMcpEntry(API, KEY, path)
    expect(claudeMcpConnected(API, path)).toBe(true)
    // A different base does not count as connected.
    expect(claudeMcpConnected('https://other.example', path)).toBe(false)
  })
})

describe('removeClaudeMcpEntry', () => {
  it('removes the entry and preserves the rest', () => {
    writeFileSync(path, JSON.stringify({ theme: 'dark' }), 'utf8')
    writeClaudeMcpEntry(API, KEY, path)
    expect(removeClaudeMcpEntry(path)).toBe(true)
    const cfg = read()
    expect(cfg.mcpServers[MCP_SERVER_KEY]).toBeUndefined()
    expect(cfg.theme).toBe('dark')
    expect(claudeMcpConnected(API, path)).toBe(false)
  })

  it('is a no-op when there is no omi entry', () => {
    writeFileSync(path, JSON.stringify({ mcpServers: {} }), 'utf8')
    expect(removeClaudeMcpEntry(path)).toBe(false)
  })
})

describe('detectClaudeCode + path', () => {
  it('claudeConfigPath sits at ~/.claude.json for the given home', () => {
    expect(claudeConfigPath('/home/u')).toBe(join('/home/u', '.claude.json'))
  })

  it('detects when a config file exists under home', () => {
    const home = join(root, 'home-with-config')
    const cfg = join(home, '.claude.json')
    mkdirSync(home, { recursive: true })
    writeFileSync(cfg, '{}', 'utf8')
    expect(detectClaudeCode(home)).toBe(true)
  })

  it('detects via ~/.claude/settings.json when there is no top-level config', () => {
    const home = join(root, 'home-with-settings')
    mkdirSync(join(home, '.claude'), { recursive: true })
    writeFileSync(join(home, '.claude', 'settings.json'), '{}', 'utf8')
    expect(detectClaudeCode(home)).toBe(true)
  })

  it('is false for an empty home with claude not on PATH', () => {
    const home = join(root, 'empty-home')
    mkdirSync(home, { recursive: true })
    // commandOnPath('claude') may be true if the dev machine has it; guard on the
    // filesystem signal by pointing at an isolated empty home and clearing PATH.
    const savedPath = process.env.PATH
    process.env.PATH = ''
    try {
      expect(detectClaudeCode(home)).toBe(false)
    } finally {
      process.env.PATH = savedPath
    }
    expect(existsSync(home)).toBe(true)
  })
})
