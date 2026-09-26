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

  it('quotes the real one-line install command when the agent has one', () => {
    // Codex and OpenClaw both have a real `npm install -g` one-liner (see
    // shared/agentGuides.ts) — the hint should hand it over verbatim instead
    // of just pointing at Settings, since that's the whole reason someone
    // reads this message: the bar told them Codex isn't connected and this is
    // the only place they're standing.
    expect(adapterActivationError('codex')).toContain('npm install -g @openai/codex')
    expect(adapterActivationError('openclaw')).toContain('npm install -g openclaw@latest')
  })

  it('falls back to the prose install note when there is no one-liner (Hermes)', () => {
    const hint = adapterActivationError('hermes')
    expect(hint).toContain('Install the Hermes CLI from its documentation.')
    expect(hint).not.toContain('npm install')
  })
})
