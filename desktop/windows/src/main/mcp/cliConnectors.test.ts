import { describe, it, expect, beforeEach, afterEach, afterAll } from 'vitest'
import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  readFileSync,
  rmSync,
  existsSync,
  statSync,
  readdirSync
} from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import {
  probeCliConnector,
  cliConnected,
  cliConnectionState,
  buildSetupCard,
  upsertCodexConfig,
  removeCodexMcpEntry,
  upsertHermesConfig,
  appendSoulNote,
  codexConfigPath
} from './cliConnectors'
import { atomicWriteFileSync } from './atomicWrite'
import { mcpServerUrl, mcpLegacyServerUrl } from '../../shared/mcpExports'

const root = mkdtempSync(join(tmpdir(), 'cli-connectors-test-'))
afterAll(() => rmSync(root, { recursive: true, force: true }))

const API = 'https://api.omi.me'
const DEV_API = 'https://api.omiapi.com'
const URL = mcpServerUrl(API)
const LEGACY_URL = mcpLegacyServerUrl(API)
const KEY = 'mcp_secret_abc'

let home: string
let n = 0
let savedPath: string | undefined
beforeEach(() => {
  home = join(root, `h${n++}`)
  mkdirSync(home, { recursive: true })
  savedPath = process.env.PATH
  process.env.PATH = '' // filesystem-only presence
})
afterEach(() => {
  process.env.PATH = savedPath
})

function codexToml(body: string): string {
  const p = codexConfigPath(home)
  mkdirSync(join(home, '.codex'), { recursive: true })
  writeFileSync(p, body, 'utf8')
  return p
}

describe('mcpServerUrl (canonical Streamable HTTP path)', () => {
  it('prod + dev bases both resolve to /v1/mcp, never the /sse alias', () => {
    expect(URL).toBe('https://api.omi.me/v1/mcp')
    expect(mcpServerUrl(DEV_API)).toBe('https://api.omiapi.com/v1/mcp')
    expect(mcpServerUrl(`${API}/`)).toBe(URL)
    expect(URL).not.toContain('sse')
  })
})

describe('probeCliConnector (presence gating, no shell)', () => {
  it('not detected when nothing is present', () => {
    expect(probeCliConnector('codex', home).detected).toBe(false)
    expect(probeCliConnector('openclaw', home).detected).toBe(false)
    expect(probeCliConnector('hermes', home).detected).toBe(false)
  })

  it('detects Codex from an existing config.toml (file-native writer)', () => {
    codexToml('[mcp_servers.other]\nurl = "https://x"\n')
    expect(probeCliConnector('codex', home).detected).toBe(true)
  })

  it('detects Hermes from ~/.hermes/config.yaml', () => {
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(join(home, '.hermes', 'config.yaml'), 'mcp_servers: {}\n', 'utf8')
    expect(probeCliConnector('hermes', home).detected).toBe(true)
  })
})

describe('cliConnected (config re-scan vs current key)', () => {
  it('codex: matches only within [mcp_servers.omi-memory] with the current bearer', () => {
    codexToml(
      `[mcp_servers.omi-memory]\nurl = "${URL}"\nhttp_headers = { Authorization = "Bearer ${KEY}" }\n`
    )
    expect(cliConnected('codex', API, KEY, home)).toBe(true)
    expect(cliConnected('codex', API, 'rotated-key', home)).toBe(false)
    expect(cliConnected('codex', DEV_API, KEY, home)).toBe(false)
  })

  it('codex: ignores a matching bearer outside the owned section', () => {
    codexToml(
      `[mcp_servers.other]\nurl = "${URL}"\nhttp_headers = { Authorization = "Bearer ${KEY}" }\n`
    )
    expect(cliConnected('codex', API, KEY, home)).toBe(false)
  })

  it('codex: ignores a commented-out or sibling-owned header', () => {
    codexToml(
      `# [mcp_servers.omi-memory]\n# url = "${URL}"\n# http_headers = { Authorization = "Bearer ${KEY}" }\n`
    )
    expect(cliConnected('codex', API, KEY, home)).toBe(false)
    codexToml(
      `[mcp_servers.omi-memory-extra]\nurl = "${URL}"\nhttp_headers = { Authorization = "Bearer ${KEY}" }\n`
    )
    expect(cliConnected('codex', API, KEY, home)).toBe(false)
  })

  it('codex: a quoted-key or subtable variant never reads as connected', () => {
    codexToml(
      `[mcp_servers."omi-memory"]\nurl = "${URL}"\nhttp_headers = { Authorization = "Bearer ${KEY}" }\n`
    )
    expect(cliConnected('codex', API, KEY, home)).toBe(false)
    codexToml(
      `[mcp_servers.omi-memory]\nurl = "${URL}"\nhttp_headers = { Authorization = "Bearer ${KEY}" }\n\n[mcp_servers.omi-memory.env]\nX = "1"\n`
    )
    expect(cliConnected('codex', API, KEY, home)).toBe(false)
  })

  it('openclaw: matches mcp.servers.omi-memory with the current bearer', () => {
    mkdirSync(join(home, '.openclaw'), { recursive: true })
    const json = {
      mcp: { servers: { 'omi-memory': { url: URL, headers: { Authorization: `Bearer ${KEY}` } } } }
    }
    writeFileSync(join(home, '.openclaw', 'openclaw.json'), JSON.stringify(json), 'utf8')
    expect(cliConnected('openclaw', API, KEY, home)).toBe(true)
    expect(cliConnected('openclaw', API, 'other', home)).toBe(false)
  })

  it('hermes: matches the owned block url + bearer', () => {
    const p = join(home, '.hermes', 'config.yaml')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(p, '', 'utf8')
    upsertHermesConfig(p, URL, KEY)
    expect(cliConnected('hermes', API, KEY, home)).toBe(true)
    expect(cliConnected('hermes', API, 'nope', home)).toBe(false)
  })

  it('hermes: ignores a matching bearer outside the owned block', () => {
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(
      join(home, '.hermes', 'config.yaml'),
      `mcp_servers:\n  other:\n    url: "${URL}"\n    headers:\n      Authorization: "Bearer ${KEY}"\n`,
      'utf8'
    )
    expect(cliConnected('hermes', API, KEY, home)).toBe(false)
  })

  it('hermes: a same-named key under another top-level key does not count', () => {
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(
      join(home, '.hermes', 'config.yaml'),
      `other_top:\n  omi-memory:\n    url: "${URL}"\n    headers:\n      Authorization: "Bearer ${KEY}"\n`,
      'utf8'
    )
    expect(cliConnected('hermes', API, KEY, home)).toBe(false)
  })

  it('hermes: duplicate mcp_servers mappings never read as connected', () => {
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(
      join(home, '.hermes', 'config.yaml'),
      `mcp_servers:\n  omi-memory:\n    url: "${URL}"\n    headers:\n      Authorization: "Bearer ${KEY}"\n\nmcp_servers:\n  other: {}\n`,
      'utf8'
    )
    expect(cliConnected('hermes', API, KEY, home)).toBe(false)
  })

  it('returns false when the config file is absent', () => {
    expect(cliConnected('codex', API, KEY, home)).toBe(false)
  })
})

describe('cliConnectionState (exact URL vs legacy /sse)', () => {
  it('codex: a same-key /v1/mcp/sse entry reads needsUpdate, not connected', () => {
    codexToml(
      `[mcp_servers.omi-memory]\nurl = "${LEGACY_URL}"\nhttp_headers = { Authorization = "Bearer ${KEY}" }\n`
    )
    expect(cliConnectionState('codex', API, KEY, home)).toBe('needsUpdate')
    expect(cliConnected('codex', API, KEY, home)).toBe(false)
    // A stale bearer on the legacy URL is just disconnected.
    expect(cliConnectionState('codex', API, 'rotated-key', home)).toBe('disconnected')
  })

  it('openclaw: a same-key /v1/mcp/sse entry reads needsUpdate', () => {
    mkdirSync(join(home, '.openclaw'), { recursive: true })
    const json = {
      mcp: {
        servers: {
          'omi-memory': { url: LEGACY_URL, headers: { Authorization: `Bearer ${KEY}` } }
        }
      }
    }
    writeFileSync(join(home, '.openclaw', 'openclaw.json'), JSON.stringify(json), 'utf8')
    expect(cliConnectionState('openclaw', API, KEY, home)).toBe('needsUpdate')
  })

  it('hermes: a same-key /v1/mcp/sse entry reads needsUpdate', () => {
    const p = join(home, '.hermes', 'config.yaml')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(p, '', 'utf8')
    upsertHermesConfig(p, LEGACY_URL, KEY)
    expect(cliConnectionState('hermes', API, KEY, home)).toBe('needsUpdate')
    expect(cliConnected('hermes', API, KEY, home)).toBe(false)
  })

  it('the canonical URL still reads connected for every CLI connector', () => {
    codexToml(
      `[mcp_servers.omi-memory]\nurl = "${URL}"\nhttp_headers = { Authorization = "Bearer ${KEY}" }\n`
    )
    expect(cliConnectionState('codex', API, KEY, home)).toBe('connected')
  })

  it('codex: a canonical URL in an unrelated field never reads as connected', () => {
    codexToml(
      `[mcp_servers.omi-memory]\nnote = "${URL}"\nhttp_headers = { Authorization = "Bearer ${KEY}" }\n`
    )
    expect(cliConnectionState('codex', API, KEY, home)).toBe('disconnected')
  })

  it('codex: conflicting canonical + legacy declarations never read as connected', () => {
    codexToml(
      `[mcp_servers.omi-memory]\nurl = "${URL}"\ncommand = "npx"\nargs = ["-y", "mcp-remote", "${LEGACY_URL}", "--header", "Authorization: Bearer ${KEY}"]\n`
    )
    expect(cliConnectionState('codex', API, KEY, home)).toBe('disconnected')
  })

  it('codex: a legacy mcp-remote args entry reads needsUpdate', () => {
    codexToml(
      `[mcp_servers.omi-memory]\ncommand = "npx"\nargs = ["-y", "mcp-remote", "${LEGACY_URL}", "--header", "Authorization: Bearer ${KEY}"]\n`
    )
    expect(cliConnectionState('codex', API, KEY, home)).toBe('needsUpdate')
  })

  it('codex: a present-but-malformed args marks ambiguity, never connected', () => {
    codexToml(
      `[mcp_servers.omi-memory]\nurl = "${URL}"\nargs = "not-an-array"\nhttp_headers = { Authorization = "Bearer ${KEY}" }\n`
    )
    expect(cliConnectionState('codex', API, KEY, home)).toBe('disconnected')
  })

  it('codex: multiple mcp-remote tokens declaring different endpoints refuse', () => {
    codexToml(
      `[mcp_servers.omi-memory]\ncommand = "npx"\nargs = ["mcp-remote", "${URL}", "mcp-remote", "${LEGACY_URL}", "--header", "Authorization: Bearer ${KEY}"]\n`
    )
    expect(cliConnectionState('codex', API, KEY, home)).toBe('disconnected')
  })

  it('openclaw: a canonical URL in a note field never reads as connected', () => {
    mkdirSync(join(home, '.openclaw'), { recursive: true })
    const json = {
      mcp: {
        servers: {
          'omi-memory': { note: URL, headers: { Authorization: `Bearer ${KEY}` } }
        }
      }
    }
    writeFileSync(join(home, '.openclaw', 'openclaw.json'), JSON.stringify(json), 'utf8')
    expect(cliConnectionState('openclaw', API, KEY, home)).toBe('disconnected')
  })

  it('openclaw: a conflicting url + mcp-remote arg never reads as connected', () => {
    mkdirSync(join(home, '.openclaw'), { recursive: true })
    const json = {
      mcp: {
        servers: {
          'omi-memory': {
            url: URL,
            args: ['-y', 'mcp-remote', LEGACY_URL, '--header', `Authorization: Bearer ${KEY}`],
            headers: { Authorization: `Bearer ${KEY}` }
          }
        }
      }
    }
    writeFileSync(join(home, '.openclaw', 'openclaw.json'), JSON.stringify(json), 'utf8')
    expect(cliConnectionState('openclaw', API, KEY, home)).toBe('disconnected')
  })

  it('openclaw: a present-but-malformed args marks ambiguity, never connected', () => {
    mkdirSync(join(home, '.openclaw'), { recursive: true })
    const json = {
      mcp: {
        servers: {
          'omi-memory': {
            url: URL,
            args: 'not-an-array',
            headers: { Authorization: `Bearer ${KEY}` }
          }
        }
      }
    }
    writeFileSync(join(home, '.openclaw', 'openclaw.json'), JSON.stringify(json), 'utf8')
    expect(cliConnectionState('openclaw', API, KEY, home)).toBe('disconnected')
  })

  it('hermes: a canonical URL in an unrelated field never reads as connected', () => {
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(
      join(home, '.hermes', 'config.yaml'),
      `mcp_servers:\n  omi-memory:\n    note: "${URL}"\n    headers:\n      Authorization: "Bearer ${KEY}"\n`,
      'utf8'
    )
    expect(cliConnectionState('hermes', API, KEY, home)).toBe('disconnected')
  })

  it('hermes: a present-but-malformed args marks ambiguity, never connected', () => {
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(
      join(home, '.hermes', 'config.yaml'),
      `mcp_servers:\n  omi-memory:\n    url: "${URL}"\n    args: not-an-array\n    headers:\n      Authorization: "Bearer ${KEY}"\n`,
      'utf8'
    )
    expect(cliConnectionState('hermes', API, KEY, home)).toBe('disconnected')
  })

  it('hermes: a legacy mcp-remote args entry reads needsUpdate', () => {
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(
      join(home, '.hermes', 'config.yaml'),
      `mcp_servers:\n  omi-memory:\n    command: npx\n    args: ["-y", "mcp-remote", "${LEGACY_URL}", "--header", "Authorization: Bearer ${KEY}"]\n`,
      'utf8'
    )
    expect(cliConnectionState('hermes', API, KEY, home)).toBe('needsUpdate')
  })
})

describe('buildSetupCard (manual fallback shows native config)', () => {
  it('codex card carries the native TOML block, not mcp-remote', () => {
    const card = buildSetupCard('codex', API, KEY)
    expect(card.copyText).toContain('[mcp_servers.omi-memory]')
    expect(card.copyText).toContain(`url = "${URL}"`)
    expect(card.copyText).toContain(`http_headers = { Authorization = "Bearer ${KEY}" }`)
    expect(card.copyText).not.toContain('mcp-remote')
    expect(card.copyText).not.toContain('npx')
    expect(card.steps.length).toBeGreaterThan(0)
  })

  it('hermes card carries the native YAML block, not npx/mcp-remote', () => {
    const card = buildSetupCard('hermes', API, KEY)
    expect(card.copyText).toContain('omi-memory:')
    expect(card.copyText).toContain(`url: "${URL}"`)
    expect(card.copyText).toContain('headers:')
    expect(card.copyText).toContain(`Authorization: "Bearer ${KEY}"`)
    expect(card.copyText).not.toContain('mcp-remote')
    expect(card.copyText).not.toContain('npx')
    expect(card.steps.length).toBeGreaterThan(0)
  })

  it('openclaw card still carries the native JSON mcp set command', () => {
    const card = buildSetupCard('openclaw', API, KEY)
    expect(card.copyText).toContain('openclaw mcp set')
    expect(card.copyText).toContain('streamable-http')
    expect(card.copyText).toContain(URL)
    expect(card.copyText).toContain(`Bearer ${KEY}`)
  })
})

describe('upsertCodexConfig (native TOML writer)', () => {
  it('creates the [mcp_servers.omi-memory] section in an empty config', () => {
    const p = join(home, '.codex', 'config.toml')
    upsertCodexConfig(p, URL, KEY)
    const text = readFileSync(p, 'utf8')
    expect(text).toBe(
      `[mcp_servers.omi-memory]\nurl = "${URL}"\nhttp_headers = { Authorization = "Bearer ${KEY}" }\n`
    )
    expect(cliConnected('codex', API, KEY, home)).toBe(true)
  })

  it('preserves unrelated sections and keys when appending', () => {
    const p = codexToml(
      'model = "gpt-5"\n\n[mcp_servers.other]\nurl = "https://other.example.com"\n'
    )
    upsertCodexConfig(p, URL, KEY)
    const text = readFileSync(p, 'utf8')
    expect(text).toContain('model = "gpt-5"')
    expect(text).toContain('[mcp_servers.other]')
    expect(text).toContain('https://other.example.com')
    expect(text).toContain('[mcp_servers.omi-memory]')
    expect(text).toContain(`url = "${URL}"`)
  })

  it('replaces the owned section on rotation without duplicating it', () => {
    const p = codexToml('')
    upsertCodexConfig(p, URL, 'old-key')
    upsertCodexConfig(p, URL, 'new-key')
    const text = readFileSync(p, 'utf8')
    expect(text.match(/\[mcp_servers\.omi-memory\]/g)?.length).toBe(1)
    expect(text).toContain('Bearer new-key')
    expect(text).not.toContain('Bearer old-key')
    expect(cliConnected('codex', API, 'new-key', home)).toBe(true)
    expect(cliConnected('codex', API, 'old-key', home)).toBe(false)
  })

  it('is idempotent — a second identical write is byte-for-byte stable', () => {
    const p = codexToml('')
    upsertCodexConfig(p, URL, KEY)
    const first = readFileSync(p, 'utf8')
    upsertCodexConfig(p, URL, KEY)
    expect(readFileSync(p, 'utf8')).toBe(first)
  })

  it('replaces a legacy mcp-remote section with the native form', () => {
    const p = codexToml(
      `[mcp_servers.omi-memory]\ncommand = "npx"\nargs = ["-y", "mcp-remote", "${URL}", "--header", "Authorization: Bearer ${KEY}"]\n`
    )
    upsertCodexConfig(p, URL, KEY)
    const text = readFileSync(p, 'utf8')
    expect(text).not.toContain('mcp-remote')
    expect(text).not.toContain('command =')
    expect(text).toContain(`url = "${URL}"`)
    expect(text).toContain('http_headers = { Authorization = "Bearer')
  })

  it('fails on a malformed owned section instead of guessing', () => {
    const p = codexToml('[mcp_servers.omi-memory]\nthis is not toml\n')
    expect(() => upsertCodexConfig(p, URL, KEY)).toThrow(/can't parse/)
    // And the file is left untouched.
    expect(readFileSync(p, 'utf8')).toContain('this is not toml')
  })

  it('fails on an ambiguous (duplicated) owned section', () => {
    const p = codexToml(
      `[mcp_servers.omi-memory]\nurl = "${URL}"\n\n[mcp_servers.omi-memory]\nurl = "https://dup"\n`
    )
    expect(() => upsertCodexConfig(p, URL, KEY)).toThrow(/ambiguous/)
  })

  it('escapes URL/key so injected quotes or newlines cannot forge TOML lines', () => {
    const p = codexToml('')
    const evilKey = 'k"\n[mcp_servers.forged]\nurl = "x'
    upsertCodexConfig(p, URL, evilKey)
    const text = readFileSync(p, 'utf8')
    // Exactly one section header — the newline inside the key stayed escaped,
    // so the forged header exists only inside the quoted scalar, never as a line.
    expect(text.match(/^\s*\[/gm)?.length).toBe(1)
    expect(text).toContain(JSON.stringify(`Bearer ${evilKey}`))
    expect(text).not.toMatch(/^\s*\[mcp_servers\.forged\]/m)
  })

  it('preserves comments and blanks sitting before the next table', () => {
    const p = codexToml(
      `[mcp_servers.omi-memory]\nurl = "https://stale"\n\n# explains the next section\n\n[mcp_servers.other]\nurl = "https://other"\n`
    )
    upsertCodexConfig(p, URL, KEY)
    const text = readFileSync(p, 'utf8')
    expect(text).toContain('# explains the next section')
    expect(text).toContain('[mcp_servers.other]')
    expect(text).toContain(`url = "${URL}"`)
    expect(text).not.toContain('https://stale')
    // The comment stays BETWEEN our section and the next table.
    expect(text).toMatch(
      /Bearer mcp_secret_abc" \}\n\n# explains the next section\n\n\[mcp_servers\.other\]/
    )
  })

  it('fails on a quoted-key alternative rather than appending a duplicate', () => {
    const p = codexToml(`[mcp_servers."omi-memory"]\nurl = "https://stale"\n`)
    expect(() => upsertCodexConfig(p, URL, KEY)).toThrow(/ambiguous/)
    expect(readFileSync(p, 'utf8')).toContain('[mcp_servers."omi-memory"]')
  })

  it('fails on a nested subtable it cannot preserve', () => {
    const p = codexToml(
      `[mcp_servers.omi-memory]\nurl = "${URL}"\n\n[mcp_servers.omi-memory.env]\nFOO = "1"\n`
    )
    expect(() => upsertCodexConfig(p, URL, 'new-key')).toThrow(/subtable/)
    expect(readFileSync(p, 'utf8')).toContain('[mcp_servers.omi-memory.env]')
  })

  it('fails on an inline omi-memory assignment inside a bare [mcp_servers] table', () => {
    const p = codexToml(
      `[mcp_servers]\nomi-memory = { url = "${URL}", http_headers = { Authorization = "Bearer ${KEY}" } }\n`
    )
    expect(() => upsertCodexConfig(p, URL, KEY)).toThrow(/ambiguous/)
    // Untouched, and never reads as connected.
    expect(readFileSync(p, 'utf8')).toContain('omi-memory = { url =')
    expect(cliConnected('codex', API, KEY, home)).toBe(false)
    expect(() => removeCodexMcpEntry(p)).toThrow(/ambiguous/)
  })

  it('fails on a dotted mcp_servers.omi-memory.url key, including quoted variants', () => {
    for (const body of [
      `mcp_servers.omi-memory.url = "${URL}"\n`,
      `mcp_servers."omi-memory".url = "${URL}"\n`,
      `"mcp_servers".omi-memory.url = "${URL}"\n`,
      `mcp_servers.omi-memory = { url = "${URL}" }\n`
    ]) {
      const p = codexToml(body)
      expect(() => upsertCodexConfig(p, URL, KEY)).toThrow(/ambiguous/)
      expect(readFileSync(p, 'utf8')).toBe(body) // untouched
      expect(cliConnected('codex', API, KEY, home)).toBe(false)
      expect(() => removeCodexMcpEntry(p)).toThrow(/ambiguous/)
    }
  })

  it('does not flag dotted keys belonging to ANOTHER table', () => {
    const p = codexToml(`[plugins]\nmcp_servers.omi-memory.url = "${URL}"\n`)
    upsertCodexConfig(p, URL, KEY)
    const text = readFileSync(p, 'utf8')
    // Their plugins.mcp_servers.… key survives; ours appends as a real table.
    expect(text).toContain('[plugins]\nmcp_servers.omi-memory.url')
    expect(text).toContain('[mcp_servers.omi-memory]')
  })

  it('writes the file 0o600 and creates ~/.codex 0o700 (Bearer key at rest)', () => {
    if (process.platform === 'win32') return
    const p = codexConfigPath(home)
    upsertCodexConfig(p, URL, KEY)
    expect(statSync(p).mode & 0o777).toBe(0o600)
    expect(statSync(join(home, '.codex')).mode & 0o777).toBe(0o700)
  })

  it('does not touch permissions of unrelated existing files', () => {
    if (process.platform === 'win32') return
    const p = codexToml('model = "gpt-5"\n')
    const sibling = join(home, '.codex', 'notes.txt')
    writeFileSync(sibling, 'x', { mode: 0o644 })
    upsertCodexConfig(p, URL, KEY)
    expect(statSync(sibling).mode & 0o777).toBe(0o644)
  })

  it('leaves the original intact and no temp residue when the rename fails', () => {
    const dir = join(home, '.codex')
    mkdirSync(dir, { recursive: true })
    const target = join(dir, 'config.toml')
    mkdirSync(target) // existing directory → renameSync fails inside atomicWrite
    expect(() => atomicWriteFileSync(target, 'content', 0o600)).toThrow()
    expect(existsSync(target)).toBe(true)
    expect(readdirSync(dir).filter((f) => f.includes('omi-tmp'))).toEqual([])
  })
})

describe('removeCodexMcpEntry', () => {
  it('removes only the owned section, preserving the rest', () => {
    const p = codexToml(
      `model = "gpt-5"\n\n[mcp_servers.omi-memory]\nurl = "${URL}"\nhttp_headers = { Authorization = "Bearer ${KEY}" }\n\n# keep me\n[mcp_servers.other]\nurl = "https://other"\n`
    )
    expect(removeCodexMcpEntry(p)).toBe(true)
    const text = readFileSync(p, 'utf8')
    expect(text).not.toContain('[mcp_servers.omi-memory]')
    expect(text).toContain('model = "gpt-5"')
    expect(text).toContain('# keep me')
    expect(text).toContain('[mcp_servers.other]')
    expect(cliConnected('codex', API, KEY, home)).toBe(false)
    expect(removeCodexMcpEntry(p)).toBe(false)
  })
})

describe('upsertHermesConfig (native YAML writer)', () => {
  it('creates a top-level mcp_servers block when absent, preserving other keys', () => {
    const p = join(home, '.hermes', 'config.yaml')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(p, 'model: sonnet\n', 'utf8')
    upsertHermesConfig(p, URL, KEY)
    const text = readFileSync(p, 'utf8')
    expect(text).toContain('model: sonnet')
    expect(text).toContain('mcp_servers:')
    expect(text).toContain('  omi-memory:')
    expect(text).toContain(`url: "${URL}"`)
    expect(text).toContain('    headers:')
    expect(text).toContain(`Authorization: "Bearer ${KEY}"`)
    expect(text).not.toContain('npx')
    expect(text).not.toContain('mcp-remote')
  })

  it('appends under an existing mcp_servers block and keeps sibling servers', () => {
    const p = join(home, '.hermes', 'config.yaml')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(p, 'mcp_servers:\n  other:\n    url: "https://other.example.com"\n', 'utf8')
    upsertHermesConfig(p, URL, KEY)
    const text = readFileSync(p, 'utf8')
    expect(text).toContain('  other:')
    expect(text).toContain('https://other.example.com')
    expect(text).toContain('  omi-memory:')
    expect(text).toContain(`url: "${URL}"`)
  })

  it('replaces an existing omi-memory sub-block (rotate) without duplicating it', () => {
    const p = join(home, '.hermes', 'config.yaml')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(p, '', 'utf8')
    upsertHermesConfig(p, URL, 'old-key')
    upsertHermesConfig(p, URL, 'new-key')
    const text = readFileSync(p, 'utf8')
    expect(text.match(/omi-memory:/g)?.length).toBe(1)
    expect(text).toContain('Bearer new-key')
    expect(text).not.toContain('Bearer old-key')
  })

  it('is idempotent — a second identical write is byte-for-byte stable', () => {
    const p = join(home, '.hermes', 'config.yaml')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(p, '', 'utf8')
    upsertHermesConfig(p, URL, KEY)
    const first = readFileSync(p, 'utf8')
    upsertHermesConfig(p, URL, KEY)
    expect(readFileSync(p, 'utf8')).toBe(first)
  })

  it('converts an empty `mcp_servers: {}` inline mapping to a block', () => {
    const p = join(home, '.hermes', 'config.yaml')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(p, 'mcp_servers: {}\nmodel: sonnet\n', 'utf8')
    upsertHermesConfig(p, URL, KEY)
    const text = readFileSync(p, 'utf8')
    // Exactly ONE mcp_servers key — a second mapping would be invalid YAML.
    expect(text.match(/^mcp_servers:/gm)?.length).toBe(1)
    expect(text).toContain('  omi-memory:')
    expect(text).toContain(`url: "${URL}"`)
    expect(text).toContain('model: sonnet')
    expect(cliConnected('hermes', API, KEY, home)).toBe(true)
  })

  it('rejects a non-empty inline mcp_servers mapping rather than clobbering it', () => {
    const p = join(home, '.hermes', 'config.yaml')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(p, 'mcp_servers: {other: {url: "https://x"}}\n', 'utf8')
    expect(() => upsertHermesConfig(p, URL, KEY)).toThrow(/inline/)
    expect(readFileSync(p, 'utf8')).toContain('mcp_servers: {other:')
  })

  it('rejects duplicate top-level mcp_servers mappings', () => {
    const p = join(home, '.hermes', 'config.yaml')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(p, 'mcp_servers:\n  a: {}\n\nmcp_servers:\n  b: {}\n', 'utf8')
    expect(() => upsertHermesConfig(p, URL, KEY)).toThrow(/duplicate/)
  })

  it('refuses a non-two-space sibling indentation, preserving the file', () => {
    const p = join(home, '.hermes', 'config.yaml')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    const original = 'mcp_servers:\n    other:\n        url: "https://other.example.com"\n'
    writeFileSync(p, original, 'utf8')
    expect(() => upsertHermesConfig(p, URL, KEY)).toThrow(/indentation/)
    expect(readFileSync(p, 'utf8')).toBe(original)
    // The same convention with an owned 4-space omi-memory block is refused on
    // the replace path too (no silent duplicate at a different indent).
    const withOwned = 'mcp_servers:\n    omi-memory:\n        url: "https://stale"\n'
    writeFileSync(p, withOwned, 'utf8')
    expect(() => upsertHermesConfig(p, URL, KEY)).toThrow(/indentation/)
    expect(readFileSync(p, 'utf8')).toBe(withOwned)
  })

  it('does not touch a same-named key nested under another top-level key', () => {
    const p = join(home, '.hermes', 'config.yaml')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(
      p,
      `other_top:\n  omi-memory:\n    url: "https://nested"\n\nmcp_servers:\n  first: {}\n`,
      'utf8'
    )
    upsertHermesConfig(p, URL, KEY)
    const text = readFileSync(p, 'utf8')
    expect(text).toContain('https://nested')
    expect(text.match(/ {2}omi-memory:/g)?.length).toBe(2) // theirs + ours
    expect(text).toContain(`url: "${URL}"`)
  })
})

describe('appendSoulNote', () => {
  it('appends a marked note once (idempotent)', () => {
    const p = join(home, 'SOUL.md')
    appendSoulNote(p)
    appendSoulNote(p)
    expect(existsSync(p)).toBe(true)
    const text = readFileSync(p, 'utf8')
    // Open + close marker written exactly once (second call is a no-op).
    expect(text.match(/omi-memory-bank/g)?.length).toBe(2)
  })
})
