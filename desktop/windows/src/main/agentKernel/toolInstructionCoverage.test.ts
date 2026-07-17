// Guard: every tool advertised to a model surface must be NAMED in that surface's
// system prompt / instruction. See toolInstructionCoverage.ts for the rule and the
// staged-enforcement design.
//
// This file is the BINDING: it derives each surface's real advertised-tool list
// and instruction text from the PRODUCTION code (not a hand-kept list), feeds them
// to the pure analyzer, prints the report, and asserts. It runs in the default
// `pnpm test` suite (and standalone via `pnpm check:tool-instruction-coverage`) so
// the current gaps are always visible.
//
// Why a Vitest test and not a standalone node script: the surface derivation pulls
// in `voiceTool.ts`, which imports `electron`. Vitest's config aliases `electron`
// to a stub (test/electronStub.ts), so these modules load; a plain `node` script
// would crash on `import 'electron'`. Vitest is the reliable runner.
//
// GREEN TODAY, ENFORCING LATER: both real surfaces are 'pending' because their
// tool-aware prose lands on sibling branches this branch is not based on
// (feat/win-voice-instruction-tools, feat/win-chat-initiative-routing). Gaps are
// reported, not failed. When a sibling branch lands, flip that surface to
// 'enforced' (one line below) and the guard verifies every advertised tool is
// named. Anti-rot: a 'pending' surface that becomes fully covered fails here with
// "flip me to enforced", so the exception cannot silently rot.

import { describe, expect, it } from 'vitest'
import {
  analyzeSurfaceCoverage,
  analyzeToolInstructionCoverage,
  formatCoverageReport,
  instructionMentions,
  type CoverageReport,
  type SurfaceCoverageInput
} from './toolInstructionCoverage'
import { omiToolManifest, toolsForAdapter } from './omiToolManifest'
import { buildVoiceHubToolCatalog } from '../ipc/voiceTool'
import { buildVoiceSystemInstruction } from '../../renderer/src/lib/voice/systemInstruction'

// ── Alias map (prose may name a tool by an alias) ──────────────────────────────
// Derived from the manifest so it never drifts from the tools themselves.
function aliasesByTool(): Record<string, string[]> {
  const map: Record<string, string[]> = {}
  for (const entry of omiToolManifest) {
    if (entry.aliases && entry.aliases.length > 0) map[entry.name] = [...entry.aliases]
  }
  return map
}

// The full tool-name universe for the REVERSE check (prose naming a real tool the
// surface does not advertise). Derived from the manifest so it never drifts.
function knownToolNames(): string[] {
  return omiToolManifest.map((entry) => entry.name)
}

// ── Surface: realtime_voice ────────────────────────────────────────────────────
// Advertised set = exactly what the production catalog builder hands the warm
// voice session. Coordinator role is the superset (the voice thread resolves
// against the coordinator-equivalent main_chat session), so it captures every tool
// a voice session could be handed. Instruction = the real voice system prompt.
function voiceSurfaceInput(): SurfaceCoverageInput {
  const advertisedTools = buildVoiceHubToolCatalog('coordinator').map((tool) => tool.name)
  const instruction = buildVoiceSystemInstruction({
    aboutUser: '<about_user>Sample user context.</about_user>',
    topLevelConversationContext: '',
    userLanguages: ['en'],
    now: new Date('2026-07-17T12:00:00Z'),
    timeZone: 'America/New_York'
  })
  return {
    surface: 'realtime_voice',
    advertisedTools,
    aliasesByTool: aliasesByTool(),
    instruction: { present: true, text: instruction },
    knownToolNames: knownToolNames(),
    // FLIP to 'enforced' when feat/win-voice-instruction-tools lands the tool
    // sections in buildVoiceSystemInstruction.
    enforcement: 'pending',
    pendingOwner: 'feat/win-voice-instruction-tools',
    allow: {}
  }
}

// ── Surface: desktopChat (desktop_chat) ────────────────────────────────────────
// Advertised set = the pi-mono coordinator projection restricted to tools declared
// on the desktop_chat surface. The prose builder (desktopChatPrompt.ts) lands on
// feat/win-chat-initiative-routing and is genuinely absent on this branch, so the
// instruction is marked not-present and every advertised tool is reported as
// unverified. When that branch lands: import its builder here, pass its rendered
// text as `instruction`, and flip enforcement to 'enforced'.
function desktopChatAdvertisedTools(): string[] {
  return toolsForAdapter('pi-mono', { executionRole: 'coordinator' })
    .filter((tool) => tool.surfaces.includes('desktop_chat'))
    .map((tool) => tool.name)
}

function desktopChatSurfaceInput(): SurfaceCoverageInput {
  return {
    surface: 'desktopChat',
    advertisedTools: desktopChatAdvertisedTools(),
    aliasesByTool: aliasesByTool(),
    knownToolNames: knownToolNames(),
    instruction: { present: false },
    // FLIP to 'enforced' (and pass the rendered prose above) when
    // feat/win-chat-initiative-routing lands the desktop-chat persona/prompt.
    enforcement: 'pending',
    pendingOwner: 'feat/win-chat-initiative-routing',
    allow: {}
  }
}

const realInputs: SurfaceCoverageInput[] = [voiceSurfaceInput(), desktopChatSurfaceInput()]
const report: CoverageReport = analyzeToolInstructionCoverage(realInputs)

// ── The check logic itself (synthetic fixtures — stable, hard asserts) ─────────
describe('analyzeSurfaceCoverage — rule encoding', () => {
  const base = {
    surface: 's',
    aliasesByTool: {},
    allow: {}
  }

  it('enforced + an unnamed advertised tool → violation (this is the bug class)', () => {
    const r = analyzeSurfaceCoverage({
      ...base,
      advertisedTools: ['spawn_agent', 'get_memories'],
      instruction: { present: true, text: 'You can spawn_agent for background work.' },
      enforcement: 'enforced'
    })
    expect(r.status).toBe('violation')
    expect(r.fails).toBe(true)
    expect(r.missing).toEqual(['get_memories'])
    expect(r.mentioned).toEqual(['spawn_agent'])
  })

  it('enforced + every advertised tool named → ok', () => {
    const r = analyzeSurfaceCoverage({
      ...base,
      advertisedTools: ['spawn_agent', 'get_memories'],
      instruction: {
        present: true,
        text: 'Use spawn_agent for work and get_memories for facts.'
      },
      enforcement: 'enforced'
    })
    expect(r.status).toBe('ok')
    expect(r.fails).toBe(false)
    expect(r.missing).toEqual([])
  })

  it('guard:allow exempts an intentionally-hidden tool', () => {
    const r = analyzeSurfaceCoverage({
      ...base,
      advertisedTools: ['spawn_agent', 'get_screenshot'],
      instruction: { present: true, text: 'Use spawn_agent for work.' },
      enforcement: 'enforced',
      allow: { get_screenshot: 'internal local-API tool, not user-facing prose' }
    })
    expect(r.status).toBe('ok')
    expect(r.allowlisted).toEqual(['get_screenshot'])
    expect(r.missing).toEqual([])
  })

  it('an alias counts as a mention', () => {
    const r = analyzeSurfaceCoverage({
      ...base,
      advertisedTools: ['semantic_search'],
      aliasesByTool: { semantic_search: ['search_screen_history'] },
      instruction: { present: true, text: 'Use search_screen_history to recall the screen.' },
      enforcement: 'enforced'
    })
    expect(r.status).toBe('ok')
    expect(r.mentioned).toEqual(['semantic_search'])
  })

  it('REVERSE: enforced + prose names a real tool the surface does NOT advertise → violation', () => {
    const r = analyzeSurfaceCoverage({
      ...base,
      advertisedTools: ['spawn_agent'],
      knownToolNames: ['spawn_agent', 'get_tasks'],
      instruction: { present: true, text: 'Use spawn_agent, and get_tasks for the list.' },
      enforcement: 'enforced'
    })
    expect(r.status).toBe('violation')
    expect(r.referencedNotAdvertised).toEqual(['get_tasks'])
    expect(r.missing).toEqual([])
  })

  it('REVERSE: only KNOWN tool names are scanned (prose tokens are not phantoms)', () => {
    const r = analyzeSurfaceCoverage({
      ...base,
      advertisedTools: ['spawn_agent'],
      knownToolNames: ['spawn_agent', 'get_tasks'],
      // about_user / screen_recording are prose tokens, not tools — must be ignored.
      instruction: {
        present: true,
        text: 'Read about_user; check screen_recording; use spawn_agent.'
      },
      enforcement: 'enforced'
    })
    expect(r.status).toBe('ok')
    expect(r.referencedNotAdvertised).toEqual([])
  })

  it('pending + gaps → reported, does not fail', () => {
    const r = analyzeSurfaceCoverage({
      ...base,
      advertisedTools: ['spawn_agent', 'get_memories'],
      instruction: { present: true, text: 'No tools named here.' },
      enforcement: 'pending',
      pendingOwner: 'some-branch'
    })
    expect(r.status).toBe('pending')
    expect(r.fails).toBe(false)
    expect(r.missing).toEqual(['spawn_agent', 'get_memories'])
  })

  it('pending + fully covered → pending-stale (FAILS: flip to enforced)', () => {
    const r = analyzeSurfaceCoverage({
      ...base,
      advertisedTools: ['spawn_agent'],
      instruction: { present: true, text: 'Use spawn_agent.' },
      enforcement: 'pending',
      pendingOwner: 'some-branch'
    })
    expect(r.status).toBe('pending-stale')
    expect(r.fails).toBe(true)
  })

  it('no instruction builder + pending → instruction-missing, does not fail', () => {
    const r = analyzeSurfaceCoverage({
      ...base,
      advertisedTools: ['spawn_agent'],
      instruction: { present: false },
      enforcement: 'pending',
      pendingOwner: 'some-branch'
    })
    expect(r.status).toBe('instruction-missing')
    expect(r.fails).toBe(false)
  })

  it('no instruction builder + enforced → violation', () => {
    const r = analyzeSurfaceCoverage({
      ...base,
      advertisedTools: ['spawn_agent'],
      instruction: { present: false },
      enforcement: 'enforced'
    })
    expect(r.status).toBe('violation')
    expect(r.fails).toBe(true)
  })
})

describe('instructionMentions — token boundary', () => {
  it('matches a standalone tool name', () => {
    expect(instructionMentions('call get_tasks now', 'get_tasks')).toBe(true)
  })
  it('does not match a longer identifier that contains the name', () => {
    expect(instructionMentions('call get_tasks_extended', 'get_tasks')).toBe(false)
  })
})

// ── The real surfaces (drift-proof derivation; report always printed) ──────────
describe('tool ↔ instruction coverage — real surfaces', () => {
  it('derives a non-empty advertised set for each surface (wiring is real)', () => {
    for (const input of realInputs) {
      expect(input.advertisedTools.length).toBeGreaterThan(0)
    }
  })

  it('prints the coverage report', () => {
    console.log(formatCoverageReport(report))
    expect(report.results.length).toBe(realInputs.length)
  })

  it('has no coverage VIOLATIONS (pending gaps are reported, not failed)', () => {
    // On a red run the printed report above names the failing surface(s).
    const failing = report.violations.map((v) => `${v.surface}: ${v.message}`)
    expect(failing).toEqual([])
  })

  it('the guard WOULD bite the real voice surface once enforced (rule is not neutered)', () => {
    // Same real inputs, enforcement flipped: today the voice prose names no tools,
    // so this must surface a violation. Proves the rule is genuinely enforcing and
    // this branch is not passing by weakening it — only by staging enforcement.
    const enforcedVoice = analyzeSurfaceCoverage({
      ...voiceSurfaceInput(),
      enforcement: 'enforced'
    })
    expect(enforcedVoice.status).toBe('violation')
    expect(enforcedVoice.missing.length).toBeGreaterThan(0)
  })
})
