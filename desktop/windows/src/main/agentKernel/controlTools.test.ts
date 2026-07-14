// Agent-control tool dispatch tests.
//
// THE LOAD-BEARING TESTS HERE ARE THE LEAF-ROLE ONES. Every leaf-gating
// assertion goes THROUGH `handleAgentControlToolCall` — the real dispatch path a
// caller uses — never by calling `executionRoleAllowsTool` directly. A predicate
// test is exactly the false comfort that let the guard sit with zero production
// callers through PR #3b while looking covered: the predicate passed, and a leaf
// agent could still call send_agent_message / spawn_agent / run_agent_and_wait.
// If someone deletes the assertLeafControlToolsAllowed call from the handler,
// these tests must fail.
//
// Driver: node:sqlite via the store's databaseFactory seam (better-sqlite3 is
// built for Electron's ABI and cannot load under plain-node Vitest). Hermetic —
// no network, no sleeps, no ordering dependence.

import { mkdtempSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { DatabaseSync } from 'node:sqlite'
import { afterEach, describe, expect, it } from 'vitest'
import { AgentRuntimeKernel } from './kernel'
import { AdapterRegistry } from './adapterRegistry'
import { SqliteAgentStore, type DatabaseFactory } from './store'
import {
  agentControlToolDefinitionsFor,
  handleAgentControlToolCall,
  isAgentControlToolName,
  AGENT_CONTROL_TOOL_NAMES,
  TRUSTED_DIRECT_CONTROL_ONLY_TOOL_NAMES,
  type AgentControlToolContext
} from './controlTools'
import { LEAF_AGENT_CONTROL_TOOLS } from './executionPolicy'

const nodeSqliteFactory = DatabaseSync as unknown as DatabaseFactory
const createdDirs: string[] = []
const openStores: SqliteAgentStore[] = []
const OWNER = 'owner-1'

afterEach(() => {
  for (const store of openStores.splice(0)) {
    try {
      store.close()
    } catch {
      // already closed
    }
  }
  for (const dir of createdDirs.splice(0)) {
    rmSync(dir, { recursive: true, force: true })
  }
})

function newKernel(): { kernel: AgentRuntimeKernel; store: SqliteAgentStore } {
  const dir = mkdtempSync(join(tmpdir(), 'omi-control-tools-'))
  createdDirs.push(dir)
  const store = new SqliteAgentStore({
    databaseFactory: nodeSqliteFactory,
    databasePath: join(dir, 'omi-agentd.sqlite3')
  })
  openStores.push(store)
  const kernel = new AgentRuntimeKernel({ store, registry: new AdapterRegistry() })
  return { kernel, store }
}

/** A trusted coordinator context — the app's own UI. */
function coordinatorContext(kernel: AgentRuntimeKernel): AgentControlToolContext {
  return {
    kernel,
    trustedUserControl: true,
    executionRole: 'coordinator',
    getOwnerId: () => OWNER
  }
}

/** A leaf worker: a background/delegated agent. Never trusted user control. */
function leafContext(kernel: AgentRuntimeKernel): AgentControlToolContext {
  return {
    kernel,
    trustedUserControl: false,
    executionRole: 'leaf',
    getOwnerId: () => OWNER
  }
}

/** A model-facing coordinator (e.g. a future tool loop): NOT trusted user control. */
function untrustedCoordinatorContext(kernel: AgentRuntimeKernel): AgentControlToolContext {
  return {
    kernel,
    trustedUserControl: false,
    executionRole: 'coordinator',
    getOwnerId: () => OWNER
  }
}

type ToolEnvelope = {
  ok: boolean
  error?: { code: string; message: string }
  [key: string]: unknown
}

async function call(
  context: AgentControlToolContext,
  name: string,
  input: Record<string, unknown> = {}
): Promise<ToolEnvelope> {
  return JSON.parse(await handleAgentControlToolCall(context, name, input)) as ToolEnvelope
}

// === INV-AGENT: leaf workers cannot spawn or message other agents ============

describe('INV-AGENT leaf-role guard (through the real dispatch path)', () => {
  // The exact set. If someone adds a spawning tool and forgets to gate it, the
  // membership test below fails.
  const LEAF_FORBIDDEN = [
    'send_agent_message',
    'spawn_background_agent',
    'spawn_agent',
    'run_agent_and_wait'
  ] as const

  it('LEAF_AGENT_CONTROL_TOOLS is exactly the four agent-fanout tools', () => {
    expect([...LEAF_AGENT_CONTROL_TOOLS].sort()).toEqual([...LEAF_FORBIDDEN].sort())
  })

  // Valid input for each forbidden tool, so a rejection can only come from the
  // role guard and never from schema validation.
  const validInput: Record<(typeof LEAF_FORBIDDEN)[number], Record<string, unknown>> = {
    send_agent_message: { sessionId: 'ses_1', prompt: 'keep going' },
    spawn_background_agent: { prompt: 'do the thing' },
    spawn_agent: { objective: 'research this' },
    run_agent_and_wait: { objective: 'compute this', parentRunId: 'run_1' }
  }

  it.each(LEAF_FORBIDDEN)('rejects a leaf caller of %s', async (name) => {
    const { kernel } = newKernel()
    const result = await call(leafContext(kernel), name, validInput[name])

    expect(result.ok).toBe(false)
    expect(result.error?.code).toBe('control_tool_failed')
    // Rejected by the ROLE guard, not by schema validation or a kernel miss.
    expect(result.error?.message).toMatch(
      name === 'send_agent_message'
        ? /Leaf workers cannot continue agent sessions\./
        : /Background agents are leaf workers and cannot start additional agents\./
    )
  })

  it.each(LEAF_FORBIDDEN)('rejects a leaf caller of %s BEFORE any kernel work', async (name) => {
    const { kernel, store } = newKernel()
    const before = store.allRows('SELECT COUNT(*) AS n FROM sessions')[0].n
    await call(leafContext(kernel), name, validInput[name])
    const after = store.allRows('SELECT COUNT(*) AS n FROM sessions')[0].n
    // A rejected leaf call must not have created a session on the way out.
    expect(after).toBe(before)
  })

  it.each(LEAF_FORBIDDEN)('lets a coordinator PAST the role guard for %s', async (name) => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), name, validInput[name])

    // These fail for a downstream reason (no adapter registered / no such
    // session) — the point is that the failure is NOT the leaf denial. A
    // coordinator is allowed through the guard.
    expect(result.error?.message ?? '').not.toMatch(/leaf workers/i)
  })

  it('a leaf caller may still use the non-forbidden tools', async () => {
    const { kernel } = newKernel()
    const result = await call(leafContext(kernel), 'list_agent_sessions', {})
    expect(result.ok).toBe(true)
  })

  it('defaults an unspecified execution role to coordinator, not leaf', async () => {
    const { kernel } = newKernel()
    const result = await call({ kernel, getOwnerId: () => OWNER }, 'spawn_agent', {
      objective: 'x'
    })
    expect(result.error?.message ?? '').not.toMatch(/leaf workers/i)
  })

  it('the deprecated canSpawnAgents=false flag still blocks spawning', async () => {
    const { kernel } = newKernel()
    const result = await call(
      { kernel, executionRole: 'coordinator', canSpawnAgents: false, getOwnerId: () => OWNER },
      'spawn_agent',
      { objective: 'x' }
    )
    expect(result.ok).toBe(false)
    expect(result.error?.message).toMatch(/cannot start additional agents/)
  })
})

// === Trusted-direct-control-only tools =======================================

describe('trusted-direct-control-only tools', () => {
  // The exact set. If someone adds a trusted-only tool and the runtime gate is
  // still hardcoded to one name, the it.each below fails for the new name.
  const TRUSTED_ONLY = ['resolve_desktop_dispatch', 'spawn_background_agent'] as const

  // Valid input for each, so a rejection can only come from the trusted-control
  // gate and never from schema validation.
  const validInput: Record<(typeof TRUSTED_ONLY)[number], Record<string, unknown>> = {
    resolve_desktop_dispatch: { dispatchId: 'dsp_1', status: 'resolved' },
    spawn_background_agent: { prompt: 'do the thing' }
  }

  it('TRUSTED_DIRECT_CONTROL_ONLY_TOOL_NAMES is exactly those two tools', () => {
    expect([...TRUSTED_DIRECT_CONTROL_ONLY_TOOL_NAMES].sort()).toEqual([...TRUSTED_ONLY].sort())
  })

  it.each(TRUSTED_ONLY)(
    'rejects an untrusted model-facing coordinator calling %s by name',
    async (name) => {
      const { kernel } = newKernel()
      // A coordinator (NOT a leaf), so the leaf-role guard does not fire — the
      // rejection can only be the trusted-control gate.
      const result = await call(untrustedCoordinatorContext(kernel), name, validInput[name])

      expect(result.ok).toBe(false)
      expect(result.error?.code).toBe('policy_denied')
      expect(result.error?.message).toBe(`${name} requires trusted user control`)
    }
  )

  it.each(TRUSTED_ONLY)('rejects an untrusted caller of %s BEFORE any kernel work', async (name) => {
    const { kernel, store } = newKernel()
    const before = store.allRows('SELECT COUNT(*) AS n FROM sessions')[0].n
    await call(untrustedCoordinatorContext(kernel), name, validInput[name])
    const after = store.allRows('SELECT COUNT(*) AS n FROM sessions')[0].n
    // In particular, a denied spawn_background_agent must not have created a session.
    expect(after).toBe(before)
  })

  it.each(TRUSTED_ONLY)('lets trusted direct control PAST the gate for %s', async (name) => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), name, validInput[name])

    // These still fail downstream (no adapter registered / no such dispatch) —
    // the point is that the failure is NOT the trusted-control denial.
    expect(result.error?.code ?? '').not.toBe('policy_denied')
  })

  it('a model-facing caller is not even shown resolve_desktop_dispatch or spawn_background_agent', () => {
    const names = agentControlToolDefinitionsFor({
      trustedUserControl: false,
      executionRole: 'coordinator'
    }).map((definition) => definition.name)

    expect(names).not.toContain('resolve_desktop_dispatch')
    expect(names).not.toContain('spawn_background_agent')
    expect(names).toContain('list_agent_sessions')
  })

  it('a model-facing LEAF caller is shown none of the four fanout tools', () => {
    const names = agentControlToolDefinitionsFor({
      trustedUserControl: false,
      executionRole: 'leaf'
    }).map((definition) => definition.name)

    for (const forbidden of LEAF_AGENT_CONTROL_TOOLS) {
      expect(names).not.toContain(forbidden)
    }
  })

  it('spawn_background_agent is never advertised on any surface', () => {
    for (const surface of ['desktopChat', 'realtimeHub'] as const) {
      const names = agentControlToolDefinitionsFor({
        trustedUserControl: true,
        executionRole: 'coordinator',
        surface
      }).map((definition) => definition.name)
      expect(names).not.toContain('spawn_background_agent')
    }
  })

  it('the published 17-name model-callable contract excludes spawn_background_agent', () => {
    // AGENT_CONTROL_TOOL_NAMES is the full 18-tool manifest; the shared contract
    // in src/shared/agentControlTools.ts is the 17 model-callable ones.
    expect(AGENT_CONTROL_TOOL_NAMES).toHaveLength(18)
    expect(AGENT_CONTROL_TOOL_NAMES).toContain('spawn_background_agent')
    expect(
      agentControlToolDefinitionsFor({ trustedUserControl: false, executionRole: 'coordinator' })
    ).toHaveLength(16) // 18 - spawn_background_agent - resolve_desktop_dispatch
  })
})

// === Unknown tools and invalid input =========================================

describe('tool-name and input validation', () => {
  it('rejects an unknown tool name', async () => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), 'rm_rf_slash', {})
    expect(result.ok).toBe(false)
    expect(result.error?.code).toBe('unknown_control_tool')
  })

  it('isAgentControlToolName recognizes exactly the manifest tools', () => {
    expect(isAgentControlToolName('list_agent_sessions')).toBe(true)
    expect(isAgentControlToolName('prepare_workstream_continuity')).toBe(false)
    expect(isAgentControlToolName('nope')).toBe(false)
  })

  // One invalid-input case per tool: a missing required field, a bad enum, or a
  // rejected extra key (every schema is strict).
  const invalidInputs: Array<[string, Record<string, unknown>]> = [
    ['list_agent_sessions', { status: 'not_a_status' }],
    ['get_agent_run', {}], // runId required
    ['build_desktop_awareness_snapshot', { limit: 9999 }], // max 200
    ['list_desktop_action_queue', { unexpected: true }], // strict object
    ['get_desktop_open_loops', { limit: -1 }],
    ['build_desktop_context_packet', { surfaceKind: 'main_chat' }], // missing objective/packetJson/ttl
    ['route_desktop_intent', { utterance: 'hi' }], // surfaceKind required
    ['evaluate_desktop_tool_policy', { selectedBundles: ['not.a.bundle'] }],
    ['create_desktop_dispatch', { kind: 'approval' }], // missing priority/title/prompt
    ['cancel_agent_run', {}], // runId required
    ['inspect_agent_artifacts', {}], // refine: needs one selector
    ['update_agent_artifact_lifecycle', { artifactId: 'art_1', state: 'incinerated' }],
    ['send_agent_message', { sessionId: 'ses_1' }], // prompt required
    ['spawn_background_agent', {}], // prompt required
    ['spawn_agent', {}], // objective required
    ['run_agent_and_wait', { objective: 'x' }], // parentRunId required
    ['set_desktop_attention_override', { subjectKind: 'run' }] // subjectId required
  ]

  it.each(invalidInputs)('returns invalid_tool_input for a bad %s call', async (name, input) => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), name, input)
    expect(result.ok).toBe(false)
    expect(result.error?.code).toBe('invalid_tool_input')
  })

  it('rejects an ownerId that does not match the active control owner', async () => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), 'list_agent_sessions', {
      ownerId: 'somebody-else'
    })
    expect(result.ok).toBe(false)
    expect(result.error?.message).toBe('Requested ownerId does not match the active control owner')
  })
})

// === Read + policy tools: happy paths ========================================

describe('read and policy tools', () => {
  it('list_agent_sessions returns the three canonical projections', async () => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), 'list_agent_sessions', {})
    expect(result.ok).toBe(true)
    expect(result.sessions).toEqual([])
    expect(result.task_agents).toEqual([])
    expect(result.floating_agent_pills).toEqual([])
  })

  it('build_desktop_awareness_snapshot reports runtime health', async () => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), 'build_desktop_awareness_snapshot', {})
    expect(result.ok).toBe(true)
    const snapshot = result.snapshot as Record<string, unknown>
    expect(snapshot.ownerId).toBe(OWNER)
    expect(snapshot.runtime).toEqual({ activeExecutionCount: 0, registeredAdapters: [] })
  })

  it('list_desktop_action_queue starts empty', async () => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), 'list_desktop_action_queue', {})
    expect(result.ok).toBe(true)
    expect(result.actionQueue).toEqual([])
  })

  it('get_desktop_open_loops returns a device-scoped, TTL-bound snapshot', async () => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), 'get_desktop_open_loops', {})
    expect(result.ok).toBe(true)
    const loops = result.openLoops as Record<string, unknown>
    expect(loops.deviceScoped).toBe(true)
    expect(loops.loops).toEqual([])
    expect(loops.expiresAtMs as number).toBeGreaterThan(loops.generatedAtMs as number)
  })

  it('a pending dispatch surfaces as an open loop and an action-queue item', async () => {
    const { kernel, store } = newKernel()
    store.insertDesktopDispatch({
      ownerId: OWNER,
      kind: 'approval',
      priority: 1,
      title: 'Share your screen?',
      decisionPrompt: 'Allow screen read?'
    })

    const queue = await call(coordinatorContext(kernel), 'list_desktop_action_queue', {})
    expect((queue.actionQueue as unknown[]).length).toBe(1)

    const result = await call(coordinatorContext(kernel), 'get_desktop_open_loops', {})
    const loops = (result.openLoops as Record<string, unknown>).loops as Array<
      Record<string, unknown>
    >
    expect(loops).toHaveLength(1)
    expect(loops[0].itemKind).toBe('dispatch')
  })

  it('route_desktop_intent routes a status question to a quick answer', async () => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), 'route_desktop_intent', {
      utterance: "what's running right now",
      surfaceKind: 'main_chat'
    })
    expect(result.ok).toBe(true)
    expect((result.route as Record<string, unknown>).intent).toBe('quick_answer')
  })

  it('evaluate_desktop_tool_policy exposes the engine without executing anything', async () => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), 'evaluate_desktop_tool_policy', {
      toolName: 'list_agent_sessions',
      selectedBundles: ['desktop.agent_control.read']
    })
    expect(result.ok).toBe(true)
    expect((result.policy as Record<string, unknown>).decision).toBe('allow')
  })

  it('evaluate_desktop_tool_policy denies a sensitive request that selected nothing', async () => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), 'evaluate_desktop_tool_policy', {
      selectedBundles: [],
      requestedBundles: ['desktop.context.screenshot_image']
    })
    expect((result.policy as Record<string, unknown>).decision).toBe('deny')
  })
})

// === Dispatch lifecycle: the consent gate ====================================

describe('dispatch create/resolve — the consent gate', () => {
  async function createApproval(
    kernel: AgentRuntimeKernel,
    overrides: Record<string, unknown> = {}
  ): Promise<string> {
    const created = await call(coordinatorContext(kernel), 'create_desktop_dispatch', {
      kind: 'approval',
      priority: 1,
      title: 'Share your screen?',
      decisionPrompt: 'Allow the agent to read the current screen?',
      capability: 'desktop.context.screenshot_image',
      operation: 'get_screenshot',
      resourceRef: 'display:1',
      ...overrides
    })
    expect(created.ok).toBe(true)
    return (created.dispatch as Record<string, unknown>).dispatchId as string
  }

  it('creates a pending dispatch', async () => {
    const { kernel } = newKernel()
    const dispatchId = await createApproval(kernel)
    expect(dispatchId).toMatch(/^disp_/)
  })

  it('resolves a dispatch and appends no grant when none was requested', async () => {
    const { kernel } = newKernel()
    const dispatchId = await createApproval(kernel)
    const result = await call(coordinatorContext(kernel), 'resolve_desktop_dispatch', {
      dispatchId,
      status: 'resolved',
      resolution: { decision: 'allow' }
    })
    expect(result.ok).toBe(true)
    expect((result.dispatch as Record<string, unknown>).status).toBe('resolved')
    expect(result.grant).toBeNull()
  })

  it('mints a scoped grant when the user explicitly allows', async () => {
    const { kernel, store } = newKernel()
    const session = store.insertSession({
      ownerId: OWNER,
      surfaceKind: 'main_chat',
      defaultAdapterId: 'acp'
    })
    const dispatchId = await createApproval(kernel, { sourceSessionId: session.sessionId })

    const result = await call(coordinatorContext(kernel), 'resolve_desktop_dispatch', {
      dispatchId,
      status: 'resolved',
      resolution: { decision: 'allow' },
      grant: {
        capability: 'desktop.context.screenshot_image',
        operation: 'get_screenshot',
        resourcePattern: 'display:1',
        expiresAtMs: Date.now() + 60_000
      }
    })

    expect(result.ok).toBe(true)
    const grant = result.grant as Record<string, unknown>
    expect(grant.capability).toBe('desktop.context.screenshot_image')
    expect(grant.sessionId).toBe(session.sessionId)
    // The approval.resolved event is appended in the SAME transaction.
    const event = result.event as Record<string, unknown>
    expect(event.type).toBe('approval.resolved')
    expect((event.payload as Record<string, unknown>).grantId).toBe(grant.grantId)
  })

  const grantRejections: Array<[string, Record<string, unknown>, RegExp]> = [
    [
      'a grant for a capability the user was never asked about',
      {
        capability: 'external.write_send',
        operation: 'get_screenshot',
        resourcePattern: 'display:1'
      },
      /capability must match the approval request/
    ],
    [
      'a grant for a different operation',
      {
        capability: 'desktop.context.screenshot_image',
        operation: 'exfiltrate',
        resourcePattern: 'display:1'
      },
      /operation must match the approval request/
    ],
    [
      'a grant for a different resource',
      {
        capability: 'desktop.context.screenshot_image',
        operation: 'get_screenshot',
        resourcePattern: 'display:99'
      },
      /resource must match the approval request/
    ]
  ]

  it.each(grantRejections)('refuses %s', async (_label, grantOverride, expected) => {
    const { kernel, store } = newKernel()
    const session = store.insertSession({
      ownerId: OWNER,
      surfaceKind: 'main_chat',
      defaultAdapterId: 'acp'
    })
    const dispatchId = await createApproval(kernel, { sourceSessionId: session.sessionId })

    const result = await call(coordinatorContext(kernel), 'resolve_desktop_dispatch', {
      dispatchId,
      status: 'resolved',
      resolution: { decision: 'allow' },
      grant: { ...grantOverride, expiresAtMs: Date.now() + 60_000 }
    })

    expect(result.ok).toBe(false)
    expect(result.error?.message).toMatch(expected)
  })

  it('refuses to mint a grant when the resolution is not an explicit allow', async () => {
    const { kernel, store } = newKernel()
    const session = store.insertSession({
      ownerId: OWNER,
      surfaceKind: 'main_chat',
      defaultAdapterId: 'acp'
    })
    const dispatchId = await createApproval(kernel, { sourceSessionId: session.sessionId })

    const result = await call(coordinatorContext(kernel), 'resolve_desktop_dispatch', {
      dispatchId,
      status: 'resolved',
      resolution: { decision: 'deny' },
      grant: {
        capability: 'desktop.context.screenshot_image',
        operation: 'get_screenshot',
        resourcePattern: 'display:1',
        expiresAtMs: Date.now() + 60_000
      }
    })

    expect(result.ok).toBe(false)
    expect(result.error?.message).toMatch(/require an allow resolution/)
  })

  it('refuses to mint a grant from a non-approval dispatch', async () => {
    const { kernel, store } = newKernel()
    const session = store.insertSession({
      ownerId: OWNER,
      surfaceKind: 'main_chat',
      defaultAdapterId: 'acp'
    })
    const dispatchId = await createApproval(kernel, {
      kind: 'routing_choice',
      sourceSessionId: session.sessionId
    })

    const result = await call(coordinatorContext(kernel), 'resolve_desktop_dispatch', {
      dispatchId,
      status: 'resolved',
      resolution: { decision: 'allow' },
      grant: {
        capability: 'desktop.context.screenshot_image',
        operation: 'get_screenshot',
        resourcePattern: 'display:1',
        expiresAtMs: Date.now() + 60_000
      }
    })

    expect(result.ok).toBe(false)
    expect(result.error?.message).toMatch(/Only approval dispatches can mint grants/)
  })

  it('a failed grant rolls back the whole resolution — no half-applied approval', async () => {
    const { kernel, store } = newKernel()
    const session = store.insertSession({
      ownerId: OWNER,
      surfaceKind: 'main_chat',
      defaultAdapterId: 'acp'
    })
    const dispatchId = await createApproval(kernel, { sourceSessionId: session.sessionId })

    await call(coordinatorContext(kernel), 'resolve_desktop_dispatch', {
      dispatchId,
      status: 'resolved',
      resolution: { decision: 'allow' },
      grant: {
        capability: 'external.write_send', // mismatched -> throws
        operation: 'get_screenshot',
        resourcePattern: 'display:1',
        expiresAtMs: Date.now() + 60_000
      }
    })

    const rows = store.allRows('SELECT status FROM desktop_dispatches WHERE dispatch_id = ?', [
      dispatchId
    ])
    expect(rows[0].status).toBe('pending')
    expect(store.allRows('SELECT COUNT(*) AS n FROM grants')[0].n).toBe(0)
  })
})

// === build_desktop_context_packet: the sensitive-context gate ================

describe('build_desktop_context_packet — sensitive context needs an approved dispatch', () => {
  const screenshotSnippet = {
    snippetId: 'snip-1',
    sourceKind: 'screenshot_image',
    operation: 'capture',
    provenance: {},
    metadata: {},
    content: 'a description of the screen',
    sensitivityTier: 'sensitive'
  }

  it('persists a benign local packet', async () => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), 'build_desktop_context_packet', {
      surfaceKind: 'main_chat',
      objective: 'summarize my day',
      ttlMs: 900_000,
      retentionClass: 'ephemeral',
      packetJson: {
        snippets: [
          {
            snippetId: 'snip-1',
            sourceKind: 'omi_db',
            operation: 'read_recent',
            sensitivityTier: 'local_private',
            content: 'benign'
          }
        ]
      }
    })
    expect(result.ok).toBe(true)
    expect(result.packet).toBeDefined()
    expect(result.accessLogs).toHaveLength(1)
  })

  it('REFUSES a sensitive screenshot snippet with no approved dispatch', async () => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), 'build_desktop_context_packet', {
      surfaceKind: 'main_chat',
      objective: 'what am I looking at',
      ttlMs: 900_000,
      retentionClass: 'ephemeral',
      packetJson: { snippets: [screenshotSnippet] }
    })

    // This is the gate that stops a screenshot reaching a model without consent.
    // It was unreachable until resolveDesktopDispatch existed to mint approvals.
    expect(result.ok).toBe(false)
    expect(result.error?.code).toBe('control_tool_failed')
  })
})

// === Serializers =============================================================

describe('serializers', () => {
  it('emits no errorCode/errorMessage noise for a healthy run', async () => {
    const { kernel, store } = newKernel()
    const session = store.insertSession({
      ownerId: OWNER,
      surfaceKind: 'main_chat',
      defaultAdapterId: 'acp'
    })
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: 'c1',
      requestId: 'r1',
      status: 'succeeded',
      mode: 'ask'
    })

    const result = await call(coordinatorContext(kernel), 'get_agent_run', { runId: run.runId })
    expect(result.ok).toBe(true)

    const serialized = result.run as Record<string, unknown>
    expect(serialized).not.toHaveProperty('errorCode')
    expect(serialized).not.toHaveProperty('errorMessage')
    // Stored *Json columns round-trip as objects, not raw strings.
    expect(serialized.input).toBeTypeOf('object')
    expect(serialized.usage).toBeTypeOf('object')
  })

  it('surfaces errorCode/errorMessage when a run actually failed', async () => {
    const { kernel, store } = newKernel()
    const session = store.insertSession({
      ownerId: OWNER,
      surfaceKind: 'main_chat',
      defaultAdapterId: 'acp'
    })
    const run = store.insertRun({
      sessionId: session.sessionId,
      clientId: 'c1',
      requestId: 'r1',
      status: 'failed',
      mode: 'ask',
      errorCode: 'adapter_crashed',
      errorMessage: 'boom'
    })

    const result = await call(coordinatorContext(kernel), 'get_agent_run', { runId: run.runId })
    const serialized = result.run as Record<string, unknown>
    expect(serialized.errorCode).toBe('adapter_crashed')
    expect(serialized.errorMessage).toBe('boom')
  })
})

// === Attention overrides =====================================================

describe('set_desktop_attention_override', () => {
  it('dismisses a subject without deleting canonical state', async () => {
    const { kernel } = newKernel()
    const result = await call(coordinatorContext(kernel), 'set_desktop_attention_override', {
      subjectKind: 'run',
      subjectId: 'run_1'
    })
    expect(result.ok).toBe(true)
    const override = result.override as Record<string, unknown>
    expect(override.subjectId).toBe('run_1')
    expect(override.dismissedAtMs).toBeTypeOf('number')
  })
})
