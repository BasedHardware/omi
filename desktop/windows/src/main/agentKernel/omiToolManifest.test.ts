// Port-parity tests for omiToolManifest.ts (macOS omi-tool-manifest.ts).
//
// The load-bearing assertions are the pi-mono projection counts and the
// leaf/coordinator gate: exactly the 3 `coordinatorOnly` control tools
// (send_agent_message, spawn_agent, run_agent_and_wait) drop for a leaf worker,
// and the trusted-direct-control-only tools (resolve_desktop_dispatch,
// spawn_background_agent) plus the onboarding-only / realtime-voice /
// local-api-only product tools are never advertised to pi-mono in any role.
//
// Hermetic — pure data + pure functions, no kernel, no store, no network.

import { describe, expect, it } from 'vitest'
import {
  buildToolAvailabilitySnapshot,
  isToolAvailableForContext,
  mcpToolDefinitionsForAdapter,
  omiToolManifest,
  productManifestEntry,
  toolNamesForAdapter,
  toolsForAdapter
} from './omiToolManifest'

const COORDINATOR_ONLY_CONTROL_TOOLS = ['send_agent_message', 'spawn_agent', 'run_agent_and_wait']
const TRUSTED_DIRECT_CONTROL_ONLY_TOOLS = ['resolve_desktop_dispatch', 'spawn_background_agent']
const ONBOARDING_ONLY_TOOLS = [
  'scan_files',
  'set_user_preferences',
  'ask_followup',
  'complete_onboarding',
  'get_email_insights'
]
const REALTIME_VOICE_ONLY_TOOLS = [
  'get_tasks',
  'create_calendar_event',
  'ask_higher_model',
  'screenshot',
  'point_click'
]
const LOCAL_API_ONLY_TOOLS = ['get_local_status', 'get_screenshot']

describe('omiToolManifest — structure', () => {
  it('holds 33 product tools + 18 control tools = 51 entries', () => {
    // 33 product drafts spliced around the 18 control tools.
    expect(omiToolManifest).toHaveLength(51)
    const names = new Set(omiToolManifest.map((tool) => tool.name))
    expect(names.size).toBe(51)
  })
})

describe('omiToolManifest — pi-mono projection counts', () => {
  it('coordinator sees 21 product + 16 control = 37 tools', () => {
    const tools = toolsForAdapter('pi-mono', { executionRole: 'coordinator' })
    expect(tools).toHaveLength(37)
    const controlCount = tools.filter((tool) => tool.executor.kind === 'runtimeControl').length
    const productCount = tools.filter((tool) => tool.executor.kind !== 'runtimeControl').length
    expect(controlCount).toBe(16)
    expect(productCount).toBe(21)
  })

  it('leaf sees 21 product + 13 control = 34 tools (the 3 coordinatorOnly tools drop)', () => {
    const tools = toolsForAdapter('pi-mono', { executionRole: 'leaf' })
    expect(tools).toHaveLength(34)
    const controlCount = tools.filter((tool) => tool.executor.kind === 'runtimeControl').length
    expect(controlCount).toBe(13)
  })

  it('the leaf/coordinator delta is exactly the 3 coordinatorOnly control tools', () => {
    const coordinator = new Set(
      toolsForAdapter('pi-mono', { executionRole: 'coordinator' }).map((tool) => tool.name)
    )
    const leaf = new Set(
      toolsForAdapter('pi-mono', { executionRole: 'leaf' }).map((tool) => tool.name)
    )
    const dropped = [...coordinator].filter((name) => !leaf.has(name))
    expect(dropped.sort()).toEqual([...COORDINATOR_ONLY_CONTROL_TOOLS].sort())
  })

  it('default context (no executionRole) matches coordinator (leaf is opt-in)', () => {
    expect(toolsForAdapter('pi-mono')).toHaveLength(37)
  })
})

describe('omiToolManifest — pi-mono exclusions', () => {
  const coordinatorNames = new Set(
    toolsForAdapter('pi-mono', { executionRole: 'coordinator' }).map((tool) => tool.name)
  )
  const leafNames = new Set(
    toolsForAdapter('pi-mono', { executionRole: 'leaf' }).map((tool) => tool.name)
  )

  it('never advertises resolve_desktop_dispatch or spawn_background_agent in either role', () => {
    for (const name of TRUSTED_DIRECT_CONTROL_ONLY_TOOLS) {
      expect(coordinatorNames.has(name)).toBe(false)
      expect(leafNames.has(name)).toBe(false)
    }
  })

  it('never advertises onboarding-only tools to pi-mono', () => {
    for (const name of ONBOARDING_ONLY_TOOLS) {
      expect(coordinatorNames.has(name)).toBe(false)
      expect(leafNames.has(name)).toBe(false)
    }
  })

  it('never advertises realtime-voice-only tools to pi-mono', () => {
    for (const name of REALTIME_VOICE_ONLY_TOOLS) {
      expect(coordinatorNames.has(name)).toBe(false)
      expect(leafNames.has(name)).toBe(false)
    }
  })

  it('never advertises local-agent-api-only tools to pi-mono', () => {
    for (const name of LOCAL_API_ONLY_TOOLS) {
      expect(coordinatorNames.has(name)).toBe(false)
      expect(leafNames.has(name)).toBe(false)
    }
  })
})

describe('omiToolManifest — other adapters', () => {
  it('advertises onboarding-only tools to the stdio adapter only under onboarding context', () => {
    const withOnboarding = new Set(
      toolsForAdapter('omi-tools-stdio', { onboarding: true }).map((tool) => tool.name)
    )
    const withoutOnboarding = new Set(
      toolsForAdapter('omi-tools-stdio', {}).map((tool) => tool.name)
    )
    for (const name of ONBOARDING_ONLY_TOOLS) {
      expect(withOnboarding.has(name)).toBe(true)
      expect(withoutOnboarding.has(name)).toBe(false)
    }
  })

  it('advertises local-api-only tools to the local-agent-api adapter', () => {
    const names = new Set(toolsForAdapter('local-agent-api').map((tool) => tool.name))
    for (const name of LOCAL_API_ONLY_TOOLS) {
      expect(names.has(name)).toBe(true)
    }
  })

  it('mcpToolDefinitionsForAdapter uses adapter-specific names and mcp schemas', () => {
    const defs = mcpToolDefinitionsForAdapter('omi-tools-stdio')
    expect(defs.length).toBeGreaterThan(0)
    for (const def of defs) {
      expect(typeof def.name).toBe('string')
      expect(typeof def.description).toBe('string')
      expect(def.inputSchema.type).toBe('object')
    }
  })
})

describe('omiToolManifest — productManifestEntry round-trip', () => {
  it('resolves a known product tool by canonical name', () => {
    const entry = productManifestEntry('execute_sql')
    expect(entry?.name).toBe('execute_sql')
  })

  it('resolves a control tool by canonical name', () => {
    expect(productManifestEntry('spawn_agent')?.name).toBe('spawn_agent')
  })

  it('resolves a product tool by alias', () => {
    expect(productManifestEntry('search_screen_history')?.name).toBe('semantic_search')
  })

  it('returns undefined for an unknown name', () => {
    expect(productManifestEntry('definitely_not_a_tool')).toBeUndefined()
  })
})

describe('omiToolManifest — isToolAvailableForContext gate', () => {
  it('coordinatorOnly is available to coordinator, not to leaf', () => {
    const availability = { advertised: true, condition: 'coordinatorOnly' as const }
    expect(isToolAvailableForContext(availability, { executionRole: 'coordinator' })).toBe(true)
    expect(isToolAvailableForContext(availability, { executionRole: 'leaf' })).toBe(false)
    expect(isToolAvailableForContext(availability, {})).toBe(true)
  })

  it('an empty adapters map (undefined availability) is never advertised', () => {
    expect(isToolAvailableForContext(undefined)).toBe(false)
  })
})

describe('omiToolManifest — availability snapshot', () => {
  it('reports the advertised count and canonical alias mapping for pi-mono coordinator', () => {
    const snapshot = buildToolAvailabilitySnapshot('pi-mono', { executionRole: 'coordinator' })
    expect(snapshot.advertisedToolCount).toBe(37)
    expect(snapshot.advertisedToolNames).toHaveLength(37)
    // Alias resolution is present for advertised tools.
    expect(snapshot.aliases['search_screen_history']).toBe('semantic_search')
    expect(snapshot.aliases['mcp__omi-tools__execute_sql']).toBe('execute_sql')
    // Excluded control tools land in the disabled set.
    const disabledNames = new Set(snapshot.disabled.map((entry) => entry.name))
    expect(disabledNames.has('resolve_desktop_dispatch')).toBe(true)
  })

  it('toolNamesForAdapter maps semantic_search to its local-agent-api adapter name', () => {
    const names = toolNamesForAdapter('local-agent-api')
    expect(names).toContain('search_screen_history')
    expect(names).not.toContain('semantic_search')
  })
})
