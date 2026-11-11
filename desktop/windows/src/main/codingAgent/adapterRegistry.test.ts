import { afterEach, describe, expect, it } from 'vitest'
import {
  ADAPTER_PROFILES,
  adapterActivationError,
  adapterConfiguredCommand,
  adapterIsActivated
} from './adapterRegistry'
import { PRODUCTION_ADAPTER_IDS } from './interface'

describe('adapterRegistry', () => {
  afterEach(() => {
    delete process.env.OMI_OPENCLAW_ADAPTER_COMMAND
    delete process.env.OMI_HERMES_ADAPTER_COMMAND
    delete process.env.OMI_CODEX_ADAPTER_COMMAND
  })

  it('registers a profile for every production adapter id', () => {
    for (const id of PRODUCTION_ADAPTER_IDS) {
      expect(ADAPTER_PROFILES[id].adapterId).toBe(id)
      expect(ADAPTER_PROFILES[id].displayName.length).toBeGreaterThan(0)
    }
  })

  it('Claude Code is always activated with no configuration', () => {
    expect(adapterIsActivated('acp')).toBe(true)
    expect(adapterConfiguredCommand('acp')).toBeUndefined()
    expect(adapterActivationError('acp')).toBeUndefined()
  })

  it('external adapters activate from their env var', () => {
    expect(adapterIsActivated('openclaw')).toBe(false)
    process.env.OMI_OPENCLAW_ADAPTER_COMMAND = 'openclaw acp'
    expect(adapterIsActivated('openclaw')).toBe(true)
    expect(adapterConfiguredCommand('openclaw')).toBe('openclaw acp')

    expect(adapterIsActivated('hermes')).toBe(false)
    expect(adapterIsActivated('codex')).toBe(false)
  })

  it('preference overrides win over env vars', () => {
    process.env.OMI_CODEX_ADAPTER_COMMAND = 'codex-from-env'
    expect(adapterConfiguredCommand('codex', { codex: 'npx @agentclientprotocol/codex-acp' })).toBe(
      'npx @agentclientprotocol/codex-acp'
    )
    // Blank/whitespace preferences fall back to the env var.
    expect(adapterConfiguredCommand('codex', { codex: '   ' })).toBe('codex-from-env')
  })

  it('produces an install hint for unconnected external adapters', () => {
    expect(adapterActivationError('hermes')).toContain('Install Hermes first')
    // Backtick-escaped: chat renders markdown, and bare underscores would be
    // eaten as italics (seen live: "OMIHERMESADAPTER_COMMAND").
    expect(adapterActivationError('hermes')).toContain('`OMI_HERMES_ADAPTER_COMMAND`')
  })
})
