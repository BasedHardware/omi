import { describe, expect, it } from 'vitest'
import { classifyTask, rankAgentsForTask } from './agentConcierge'
import type { AgentOutcomeEntry } from './agentOutcomeLedger'

describe('classifyTask', () => {
  it('tags a wide multi-file ask as bulk_refactor', () => {
    expect(classifyTask('refactor this across the codebase')).toBe('bulk_refactor')
    expect(classifyTask('migrate every file to the new API')).toBe('bulk_refactor')
  })

  it('tags an unattended/background ask as long_running', () => {
    expect(classifyTask("keep working on this while I'm away")).toBe('long_running')
    expect(classifyTask('run this overnight')).toBe('long_running')
  })

  it('tags a lookup/comparison ask as research', () => {
    expect(classifyTask("research what's the best approach for pagination")).toBe('research')
  })

  it('tags a small one-shot ask as quick_script', () => {
    expect(classifyTask('write a quick one-liner to rename this file')).toBe('quick_script')
  })

  it('falls back to general for anything that matches nothing', () => {
    expect(classifyTask('what time is it')).toBe('general')
  })

  it('prefers long_running over a bulk_refactor phrase in the same prompt', () => {
    // Resumability is the more consequential property to route on: an agent
    // that can't survive a restart loses the whole run, where one that's
    // merely mediocre at big-scope edits still finishes it.
    expect(classifyTask('refactor this across the codebase overnight')).toBe('long_running')
  })
})

describe('rankAgentsForTask', () => {
  it('puts Claude Code first among connected agents with no distinguishing history', () => {
    // acp gets the built-in bonus and full tool support; nobody outscores it
    // on a plain task. hermes/codex tie at a neutral baseline and keep input
    // order; openclaw's real, matrix-documented lack of tool support
    // (ADAPTER_CAPABILITY_MATRIX.openclaw.toolSupport) drops it last.
    expect(
      rankAgentsForTask(['acp', 'openclaw', 'hermes', 'codex'], 'fix the failing test', [])
    ).toEqual(['acp', 'hermes', 'codex', 'openclaw'])
  })

  it('breaks a score tie by input order, not alphabetically or randomly', () => {
    expect(rankAgentsForTask(['codex', 'hermes'], 'just chatting', [])).toEqual(['codex', 'hermes'])
    expect(rankAgentsForTask(['hermes', 'codex'], 'just chatting', [])).toEqual(['hermes', 'codex'])
  })

  it('lets a task-relevant capability override plain input order', () => {
    // Hermes documents session/set_model support (modelSwitching: required);
    // Codex's is an unverified known_limitation. For a bulk refactor — where
    // being able to size the model to the job matters — that's a real,
    // sourced reason to prefer Hermes, even though Codex was listed first.
    expect(rankAgentsForTask(['codex', 'hermes'], 'refactor this across the codebase', [])).toEqual(
      ['hermes', 'codex']
    )
  })

  it('lets a winning streak move an agent ahead of an input-order tie', () => {
    const ledger: AgentOutcomeEntry[] = Array.from({ length: 3 }, (_, i) => ({
      adapterId: 'codex',
      tag: 'general',
      outcome: 'success',
      ts: i
    }))
    expect(rankAgentsForTask(['hermes', 'codex'], 'just chatting', ledger)).toEqual([
      'codex',
      'hermes'
    ])
  })

  it('only weighs the most recent matching attempts, so a stale bad stretch clears out', () => {
    const staleFailures: AgentOutcomeEntry[] = Array.from({ length: 15 }, (_, i) => ({
      adapterId: 'codex',
      tag: 'general',
      outcome: 'failure',
      ts: i
    }))
    const recentWins: AgentOutcomeEntry[] = Array.from({ length: 10 }, (_, i) => ({
      adapterId: 'codex',
      tag: 'general',
      outcome: 'success',
      ts: 1000 + i
    }))
    // Only the most recent 20 of these 25 entries count: the oldest 5
    // failures fall out of the window, leaving 10 failures + 10 wins — a
    // wash, not a net negative — so the input-order tie-break decides rather
    // than a month-old streak permanently outranking Hermes.
    expect(
      rankAgentsForTask(['codex', 'hermes'], 'just chatting', [...staleFailures, ...recentWins])
    ).toEqual(['codex', 'hermes'])
  })

  it('caps history so a winning streak cannot promote a tool-less agent over the built-in default', () => {
    const allWins: AgentOutcomeEntry[] = Array.from({ length: 20 }, (_, i) => ({
      adapterId: 'openclaw',
      tag: 'general',
      outcome: 'success',
      ts: i
    }))
    // OpenClaw's real, matrix-documented gap (it can't call tools at all) is
    // bigger than the ledger's max swing, on purpose — a lucky streak nudges,
    // it never fully overrides a structural capability gap.
    expect(rankAgentsForTask(['openclaw', 'acp'], 'just chatting', allWins)).toEqual([
      'acp',
      'openclaw'
    ])
  })

  it('ignores history for a different agent or a different kind of task', () => {
    const ledger: AgentOutcomeEntry[] = [
      { adapterId: 'codex', tag: 'bulk_refactor', outcome: 'success', ts: 1 },
      { adapterId: 'codex', tag: 'bulk_refactor', outcome: 'success', ts: 2 }
    ]
    // Same codex win streak as the earlier test, but recorded against a
    // different task tag — must not leak into an unrelated 'general' ranking.
    expect(rankAgentsForTask(['hermes', 'codex'], 'just chatting', ledger)).toEqual([
      'hermes',
      'codex'
    ])
  })
})
