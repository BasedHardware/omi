// Capability-bundle / grant policy engine tests.
//
// The engine is pure: plain data in, plain data out. `Date.now()` is its only
// non-deterministic call and every test injects `nowMs`, so there are no sleeps,
// no clock flake, and no ordering dependence between tests.

import { describe, expect, it } from 'vitest'
import {
  bundlesForOmiTool,
  descriptorFromOmiTool,
  desktopToolPolicyInternals,
  evaluateDesktopToolPolicy,
  type DesktopCoordinatorBundle,
  type DesktopToolGrant
} from './desktopToolPolicy'

const NOW = 1_000_000

function grant(overrides: Partial<DesktopToolGrant> = {}): DesktopToolGrant {
  return {
    bundle: 'desktop.context.screenshot_image',
    expiresAtMs: NOW + 60_000,
    effect: 'allow',
    ...overrides
  }
}

describe('evaluateDesktopToolPolicy — deny by default', () => {
  it('denies a request that declares no capability bundle at all', () => {
    const result = evaluateDesktopToolPolicy({ selectedBundles: [], nowMs: NOW })
    expect(result.decision).toBe('deny')
    expect(result.reason).toBe('No coordinator capability bundle was declared.')
  })

  it('denies an unknown tool name — it resolves to zero bundles, not to an allow', () => {
    const result = evaluateDesktopToolPolicy({
      toolName: 'definitely_not_a_tool',
      selectedBundles: ['desktop.agent_control.read'],
      nowMs: NOW
    })
    expect(result.decision).toBe('deny')
    expect(result.reason).toBe('No coordinator capability bundle was declared.')
  })

  it('denies when a required bundle was not selected, and names the missing bundles', () => {
    const result = evaluateDesktopToolPolicy({
      toolName: 'list_agent_sessions',
      selectedBundles: [],
      nowMs: NOW
    })
    expect(result.decision).toBe('deny')
    expect(result.reason).toBe('Missing selected bundle(s): desktop.agent_control.read')
  })

  it('selection is a precondition — a permitted tool is still denied without it', () => {
    const result = evaluateDesktopToolPolicy({
      toolName: 'build_desktop_context_packet',
      selectedBundles: ['desktop.context.local_read'], // screen_summary missing
      nowMs: NOW
    })
    expect(result.decision).toBe('deny')
    expect(result.reason).toBe('Missing selected bundle(s): desktop.context.screen_summary')
  })
})

describe('evaluateDesktopToolPolicy — allow', () => {
  it('allows a read-only local operation whose bundles are selected', () => {
    const result = evaluateDesktopToolPolicy({
      toolName: 'list_agent_sessions',
      selectedBundles: ['desktop.agent_control.read'],
      nowMs: NOW
    })
    expect(result.decision).toBe('allow')
    expect(result.reason).toBe('Selected bundles allow this read-only local operation.')
    expect(result.descriptor.readOnly).toBe(true)
    expect(result.descriptor.riskTier).toBe('low')
  })
})

describe('evaluateDesktopToolPolicy — hard denies that no bundle or grant can override', () => {
  it('denies a SQL write through a read context tool', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.context.local_read'],
      requestedBundles: ['desktop.context.local_read'],
      sql: 'DELETE FROM conversations',
      nowMs: NOW
    })
    expect(result.decision).toBe('deny')
    expect(result.reason).toBe('SQL writes are not allowed through read context tools.')
  })

  it('a SQL write is denied even when a live allow grant covers the bundle', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.context.local_read'],
      requestedBundles: ['desktop.context.local_read'],
      sql: 'INSERT INTO memories VALUES (1)',
      grants: [grant({ bundle: 'desktop.context.local_read' })],
      nowMs: NOW
    })
    expect(result.decision).toBe('deny')
    expect(result.reason).toBe('SQL writes are not allowed through read context tools.')
  })

  it('allows a plain SELECT', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.context.local_read'],
      requestedBundles: ['desktop.context.local_read'],
      sql: 'SELECT * FROM conversations',
      nowMs: NOW
    })
    expect(result.decision).toBe('allow')
  })

  it('classifies a write hidden behind a comment as a write', () => {
    expect(desktopToolPolicyInternals.isSqlWrite('-- harmless\nDROP TABLE memories')).toBe(true)
    expect(desktopToolPolicyInternals.isSqlWrite('/* x */ SELECT 1')).toBe(false)
    expect(desktopToolPolicyInternals.isSqlWrite('WITH t AS (SELECT 1) DELETE FROM t')).toBe(true)
  })

  it('denies dev-only automation actuation outside a dev bundle', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.automation.act_dev_only'],
      requestedBundles: ['desktop.automation.act_dev_only'],
      nowMs: NOW
    })
    expect(result.decision).toBe('deny')
    expect(result.reason).toBe(
      'Desktop automation actuation is only available in dev/test bundles.'
    )
  })

  it('routes dev-only automation to dispatch inside a dev bundle', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.automation.act_dev_only'],
      requestedBundles: ['desktop.automation.act_dev_only'],
      isDevBundle: true,
      nowMs: NOW
    })
    expect(result.decision).toBe('dispatch_required')
  })
})

describe('evaluateDesktopToolPolicy — dispatch_required', () => {
  const sensitiveTriggers: Array<[string, Record<string, unknown>]> = [
    ['screenshot image bytes', { includesScreenshotImageBytes: true }],
    ['broad screen history', { broadScreenHistory: true }],
    ['external send', { externalSend: true }],
    ['persistent grant', { persistentGrant: true }]
  ]

  it.each(sensitiveTriggers)('requires dispatch for %s', (_label, trigger) => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.context.local_read'],
      requestedBundles: ['desktop.context.local_read'],
      nowMs: NOW,
      ...trigger
    })
    expect(result.decision).toBe('dispatch_required')
    expect(result.reason).toBe('Sensitive action requires dispatch or scoped grant.')
  })

  const sensitiveBundles: DesktopCoordinatorBundle[] = [
    'desktop.context.screenshot_image',
    'external.write_send',
    'desktop.permissions.request'
  ]

  it.each(sensitiveBundles)('requires dispatch for the %s bundle', (bundle) => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: [bundle],
      requestedBundles: [bundle],
      nowMs: NOW
    })
    expect(result.decision).toBe('dispatch_required')
  })

  it('requires dispatch for a user_approval tool (build_desktop_context_packet)', () => {
    const result = evaluateDesktopToolPolicy({
      toolName: 'build_desktop_context_packet',
      selectedBundles: ['desktop.context.local_read', 'desktop.context.screen_summary'],
      nowMs: NOW
    })
    expect(result.decision).toBe('dispatch_required')
    expect(result.descriptor.approvalPolicy).toBe('user_approval')
  })

  it('requires dispatch for a policy_grant tool (spawn_agent)', () => {
    const result = evaluateDesktopToolPolicy({
      toolName: 'spawn_agent',
      selectedBundles: ['desktop.agent_control.manage'],
      nowMs: NOW
    })
    expect(result.decision).toBe('dispatch_required')
    expect(result.descriptor.approvalPolicy).toBe('policy_grant')
  })

  it('routes an explicit user task mutation to a durable approval record', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.tasks.readwrite'],
      requestedBundles: ['desktop.tasks.readwrite'],
      userExplicitMutation: true,
      nowMs: NOW
    })
    expect(result.decision).toBe('dispatch_required')
    expect(result.reason).toBe('Task mutation still needs a durable approval record.')
  })
})

describe('evaluateDesktopToolPolicy — scoped grants', () => {
  it('a live allow grant covering every required bundle turns dispatch into allow', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.context.screenshot_image'],
      requestedBundles: ['desktop.context.screenshot_image'],
      grants: [grant()],
      nowMs: NOW
    })
    expect(result.decision).toBe('allow')
    expect(result.reason).toBe('Scoped allow grant covers the request.')
  })

  it('an expired grant does not cover the request', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.context.screenshot_image'],
      requestedBundles: ['desktop.context.screenshot_image'],
      grants: [grant({ expiresAtMs: NOW - 1 })],
      nowMs: NOW
    })
    expect(result.decision).toBe('dispatch_required')
  })

  it('expiry is strict — a grant expiring exactly now is already expired', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.context.screenshot_image'],
      requestedBundles: ['desktop.context.screenshot_image'],
      grants: [grant({ expiresAtMs: NOW })],
      nowMs: NOW
    })
    expect(result.decision).toBe('dispatch_required')
  })

  it('a deny-effect grant never covers the request', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.context.screenshot_image'],
      requestedBundles: ['desktop.context.screenshot_image'],
      grants: [grant({ effect: 'deny' })],
      nowMs: NOW
    })
    expect(result.decision).toBe('dispatch_required')
  })

  it('a grant for a different bundle does not cover the request', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.context.screenshot_image'],
      requestedBundles: ['desktop.context.screenshot_image'],
      grants: [grant({ bundle: 'desktop.context.local_read' })],
      nowMs: NOW
    })
    expect(result.decision).toBe('dispatch_required')
  })

  it('EVERY required bundle must be granted — a partial grant is not enough', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.context.screenshot_image', 'external.write_send'],
      requestedBundles: ['desktop.context.screenshot_image', 'external.write_send'],
      grants: [grant()], // covers screenshot_image only
      nowMs: NOW
    })
    expect(result.decision).toBe('dispatch_required')
  })

  it('an operation-scoped grant only covers its own operation', () => {
    const base = {
      selectedBundles: ['desktop.context.screenshot_image'] as DesktopCoordinatorBundle[],
      requestedBundles: ['desktop.context.screenshot_image'] as DesktopCoordinatorBundle[],
      grants: [grant({ operation: 'get_screenshot' })],
      nowMs: NOW
    }
    expect(evaluateDesktopToolPolicy({ ...base, operation: 'get_screenshot' }).decision).toBe(
      'allow'
    )
    expect(evaluateDesktopToolPolicy({ ...base, operation: 'capture_screen' }).decision).toBe(
      'dispatch_required'
    )
  })

  it('a resource-scoped grant only covers its own resource', () => {
    const base = {
      selectedBundles: ['desktop.context.screenshot_image'] as DesktopCoordinatorBundle[],
      requestedBundles: ['desktop.context.screenshot_image'] as DesktopCoordinatorBundle[],
      grants: [grant({ resourceRef: 'display:1' })],
      nowMs: NOW
    }
    expect(evaluateDesktopToolPolicy({ ...base, resourceRef: 'display:1' }).decision).toBe('allow')
    expect(evaluateDesktopToolPolicy({ ...base, resourceRef: 'display:2' }).decision).toBe(
      'dispatch_required'
    )
  })

  it('a grant with no operation/resource is a wildcard on those dimensions', () => {
    const result = evaluateDesktopToolPolicy({
      selectedBundles: ['desktop.context.screenshot_image'],
      requestedBundles: ['desktop.context.screenshot_image'],
      operation: 'anything',
      resourceRef: 'anywhere',
      grants: [grant()],
      nowMs: NOW
    })
    expect(result.decision).toBe('allow')
  })
})

describe('product-tool bundle mapping (ported for the track that lands those tools)', () => {
  const entry = (name: string, readOnlyHint = false, destructiveHint = false) => ({
    name,
    executor: { kind: 'swiftTool' },
    annotations: { readOnlyHint, destructiveHint }
  })

  it('maps screen-image tools to the screenshot_image bundle', () => {
    expect(bundlesForOmiTool(entry('capture_screen'))).toEqual(['desktop.context.screenshot_image'])
  })

  it('maps request_permission to the 12th coordinator-wide bundle', () => {
    expect(bundlesForOmiTool(entry('request_permission'))).toEqual(['desktop.permissions.request'])
  })

  it('falls back to local_read for an unmapped read-only tool', () => {
    expect(bundlesForOmiTool(entry('some_other_read', true))).toEqual([
      'desktop.context.local_read'
    ])
  })

  it('leaves an unmapped write tool with zero bundles, so the engine denies it', () => {
    expect(bundlesForOmiTool(entry('mystery_write'))).toEqual([])
  })

  it('marks a screenshot tool sensitive and high risk', () => {
    const descriptor = descriptorFromOmiTool(entry('get_screenshot'))
    expect(descriptor.riskTier).toBe('high')
    expect(descriptor.privacyTier).toBe('sensitive')
    expect(descriptor.approvalPolicy).toBe('user_approval')
  })
})
