import { describe, it, expect, beforeEach, afterEach, afterAll } from 'vitest'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { probeCliConnector } from './cliConnectors'

const root = mkdtempSync(join(tmpdir(), 'cli-connectors-test-'))
afterAll(() => rmSync(root, { recursive: true, force: true }))

let savedPath: string | undefined
beforeEach(() => {
  savedPath = process.env.PATH
  process.env.PATH = '' // nothing on PATH → CLI presence is filesystem-only
})
afterEach(() => {
  process.env.PATH = savedPath
})

describe('probeCliConnector (presence gating, no shell)', () => {
  it('reports not-detected for every connector when nothing is present', () => {
    const emptyHome = join(root, 'empty')
    mkdirSync(emptyHome, { recursive: true })
    expect(probeCliConnector('codex', emptyHome).detected).toBe(false)
    expect(probeCliConnector('openclaw', emptyHome).detected).toBe(false)
    expect(probeCliConnector('hermes', emptyHome).detected).toBe(false)
  })

  it('detects Hermes from its ~/.hermes/config.yaml even with an empty PATH', () => {
    const home = join(root, 'with-hermes')
    mkdirSync(join(home, '.hermes'), { recursive: true })
    writeFileSync(join(home, '.hermes', 'config.yaml'), 'mcp_servers: {}\n', 'utf8')
    expect(probeCliConnector('hermes', home).detected).toBe(true)
  })

  it('marks only Codex as writable (OpenClaw/Hermes config-write pending)', () => {
    expect(probeCliConnector('codex', root).writable).toBe(true)
    expect(probeCliConnector('openclaw', root).writable).toBe(false)
    expect(probeCliConnector('hermes', root).writable).toBe(false)
  })
})
