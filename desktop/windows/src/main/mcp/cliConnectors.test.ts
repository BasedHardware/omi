import { describe, it, expect, beforeEach, afterEach, afterAll } from 'vitest'
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, existsSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import {
  probeCliConnector,
  cliConnected,
  buildSetupCard,
  upsertHermesConfig,
  appendSoulNote
} from './cliConnectors'
import { mcpServerUrl } from '../../shared/mcpExports'

const root = mkdtempSync(join(tmpdir(), 'cli-connectors-test-'))
afterAll(() => rmSync(root, { recursive: true, force: true }))

const API = 'https://api.omi.me'
const URL = mcpServerUrl(API)
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

describe('probeCliConnector (presence gating, no shell)', () => {
  it('not detected when nothing is present', () => {
    expect(probeCliConnector('codex', home).detected).toBe(false)
    expect(probeCliConnector('openclaw', home).detected).toBe(false)
    expect(probeCliConnector('hermes', home).detected).toBe(false)
  })

  it('detects Hermes from ~/.hermes/config.yaml', () => {
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(join(home, '.hermes', 'config.yaml'), 'mcp_servers: {}\n', 'utf8')
    expect(probeCliConnector('hermes', home).detected).toBe(true)
  })
})

describe('cliConnected (config re-scan vs current key)', () => {
  it('codex: matches only within [mcp_servers.omi-memory] with the current bearer', () => {
    mkdirSync(join(home, '.codex'), { recursive: true })
    const toml = `[mcp_servers.omi-memory]\ncommand = "npx"\nargs = ["-y","mcp-remote","${URL}","--header","Authorization: Bearer ${KEY}"]\n`
    writeFileSync(join(home, '.codex', 'config.toml'), toml, 'utf8')
    expect(cliConnected('codex', API, KEY, home)).toBe(true)
    expect(cliConnected('codex', API, 'rotated-key', home)).toBe(false)
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

  it('hermes: matches the config.yaml url + bearer', () => {
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(join(home, '.hermes', 'config.yaml'), '', 'utf8')
    upsertHermesConfig(join(home, '.hermes', 'config.yaml'), URL, KEY)
    expect(cliConnected('hermes', API, KEY, home)).toBe(true)
    expect(cliConnected('hermes', API, 'nope', home)).toBe(false)
  })

  it('returns false when the config file is absent', () => {
    expect(cliConnected('codex', API, KEY, home)).toBe(false)
  })
})

describe('buildSetupCard', () => {
  it('embeds the url + key in each tool’s copy text', () => {
    for (const id of ['codex', 'openclaw', 'hermes'] as const) {
      const card = buildSetupCard(id, API, KEY)
      expect(card.copyText).toContain(URL)
      expect(card.copyText).toContain(`Bearer ${KEY}`)
      expect(card.steps.length).toBeGreaterThan(0)
    }
  })
})

describe('upsertHermesConfig', () => {
  it('creates a top-level mcp_servers block when absent, preserving other keys', () => {
    const p = join(home, '.hermes', 'config.yaml')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(p, 'model: sonnet\n', 'utf8')
    upsertHermesConfig(p, URL, KEY)
    const text = readFileSync(p, 'utf8')
    expect(text).toContain('model: sonnet')
    expect(text).toContain('mcp_servers:')
    expect(text).toContain('  omi-memory:')
    expect(text).toContain(URL)
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
