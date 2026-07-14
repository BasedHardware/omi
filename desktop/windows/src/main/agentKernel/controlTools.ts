// Agent-control tool dispatch — Windows port of the macOS agent runtime's
// control-tools.ts (desktop/macos/agent/src/runtime/).
//
// Zod schemas for the 18 manifest tools, the `handleAgentControlToolCall`
// dispatch switch, and the entity serializers. This is the single boundary every
// control-tool call passes through, and therefore the enforcement point for the
// INV-AGENT leaf-role guard (see `assertLeafControlToolsAllowed` below).
//
// Windows deltas from the macOS original:
//   - No JSONL/stdio transport. The kernel runs in-process in Electron main, so
//     tool results return by direct function call. macOS' tool-correlation.ts
//     (which maps a tool call back onto an outbound protocol message) has no
//     equivalent and is deliberately not ported.
//   - No `buildMcpServers`. macOS builds MCP server configs to hand to a
//     subprocess ACP adapter over that same transport. Windows does not host an
//     MCP server, so control-initiated runs pass no `mcpServers` — the kernel's
//     input types already treat it as optional.
//   - The five `*_workstream_continuity` internal RPCs are not ported (the
//     workstream model is owned by another track). This file therefore has 18
//     schemas, not macOS' 23.

import { randomUUID } from 'node:crypto'
import { z } from 'zod'
import { isProductionAdapterId } from '../codingAgent/interface'
import type {
  AdapterBinding,
  AgentArtifact,
  AgentDelegation,
  AgentEvent,
  AgentRun,
  AgentSession,
  RunAttempt
} from './types'
import type { AgentRuntimeKernel } from './kernel'
import type { DesktopAwarenessSnapshot, ExecuteAgentRunInput } from './kernelTypes'
import { agentControlCapabilityManifest, agentControlInputSchema } from './controlToolManifest'
import { evaluateDesktopToolPolicy, type DesktopCoordinatorBundle } from './desktopToolPolicy'
import {
  assertAgentSpawningAllowed,
  assertLeafControlToolsAllowed,
  providerBoundaryForAdapter,
  resolveAdapterWithinBoundary,
  type AgentExecutionRole,
  type ProviderBoundary
} from './executionPolicy'

const sessionStatusSchema = z.enum(['open', 'archived', 'closed'])
const agentSurfaceKindSchema = z.enum([
  'main_chat',
  'task_chat',
  'realtime',
  'delegated_agent',
  'background_agent',
  'floating_bar',
  'floating_pill'
])
const artifactRoleSchema = z.enum(['input', 'result', 'checkpoint', 'tool_output', 'log', 'other'])
const artifactLifecycleStateSchema = z.enum(['retained', 'dismissed', 'opened'])
const runModeSchema = z.enum(['ask', 'act'])
const desktopCoordinatorBundleSchema = z.enum([
  'desktop.agent_control.read',
  'desktop.agent_control.manage',
  'desktop.context.local_read',
  'desktop.context.screen_summary',
  'desktop.context.screenshot_image',
  'desktop.tasks.readwrite',
  'desktop.artifacts.manage',
  'desktop.automation.read',
  'desktop.automation.act_dev_only',
  'external.write_prepare',
  'external.write_send'
])
const strictObject = <T extends z.ZodRawShape>(shape: T): z.ZodObject<T> => z.object(shape).strict()

const listAgentSessionsSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  status: sessionStatusSchema.optional(),
  surfaceKind: agentSurfaceKindSchema.optional(),
  limit: z.coerce.number().int().positive().max(200).default(50),
  beforeUpdatedAtMs: z.coerce.number().int().positive().optional()
})

const getAgentRunSchema = strictObject({
  runId: z.string().min(1),
  ownerId: z.string().min(1).optional(),
  includeEvents: z.boolean().default(true),
  eventLimit: z.coerce.number().int().positive().max(500).default(100)
})

const buildDesktopAwarenessSnapshotSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  limit: z.coerce.number().int().positive().max(200).default(50)
})

const listDesktopActionQueueSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  staleAfterMs: z.coerce.number().int().positive().optional(),
  limit: z.coerce.number().int().positive().max(200).default(50)
})

const getDesktopOpenLoopsSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  limit: z.coerce.number().int().positive().max(200).default(50)
})

const contextSnippetSchema = strictObject({
  snippetId: z.string().min(1),
  sourceKind: z.enum([
    'omi_db',
    'rewind_timeline',
    'screen_current',
    'screenshot_image',
    'local_agent_api',
    'automation_bridge',
    'chat_surface',
    'task_chat'
  ]),
  operation: z.string().min(1),
  provenance: z.record(z.string(), z.unknown()).default({}),
  content: z.string().optional(),
  redactedContent: z.string().optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
  sensitivityTier: z.string().min(1),
  policyDecision: z.enum(['allowed', 'denied', 'dispatch_created']).optional(),
  dispatchId: z.string().min(1).nullable().optional(),
  selected: z.boolean().optional(),
  tokenEstimate: z.coerce.number().int().positive().optional()
})

const buildDesktopContextPacketSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  sessionId: z.string().min(1).nullable().optional(),
  runId: z.string().min(1).nullable().optional(),
  surfaceKind: z.string().min(1),
  objective: z.string().min(1),
  packetJson: strictObject({
    snippets: z.array(contextSnippetSchema).default([]),
    selectedToolBundles: z.array(desktopCoordinatorBundleSchema).default([]),
    constraints: z.array(z.string()).default([]),
    evidenceRequired: z.array(z.string()).default([]),
    boundaryPolicy: z.record(z.string(), z.unknown()).default({})
  }),
  ttlMs: z.coerce.number().int().positive(),
  retentionClass: z.enum(['ephemeral', 'debug', 'core'])
})

const routeDesktopIntentSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  utterance: z.string().min(1),
  surfaceKind: z.string().min(1),
  taskId: z.string().min(1).nullable().optional()
})

const evaluateDesktopToolPolicySchema = strictObject({
  // Direct app control authenticates the caller through an owner guard that is
  // merged into every strict control-tool input before dispatch.
  ownerId: z.string().min(1).optional(),
  toolName: z.string().min(1).optional(),
  selectedBundles: z.array(desktopCoordinatorBundleSchema),
  requestedBundles: z.array(desktopCoordinatorBundleSchema).optional(),
  sql: z.string().optional(),
  operation: z.string().optional(),
  resourceRef: z.string().optional(),
  includesScreenshotImageBytes: z.boolean().optional(),
  broadScreenHistory: z.boolean().optional(),
  externalSend: z.boolean().optional(),
  persistentGrant: z.boolean().optional(),
  isDevBundle: z.boolean().optional()
})

const createDesktopDispatchSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  kind: z.enum([
    'approval',
    'routing_choice',
    'failure_recovery',
    'artifact_review',
    'memory_candidate',
    'task_candidate',
    'external_draft',
    'screen_context'
  ]),
  priority: z.coerce.number().int(),
  title: z.string().min(1),
  decisionPrompt: z.string().min(1),
  recommendedDefault: z.string().nullable().optional(),
  sourceSessionId: z.string().min(1).nullable().optional(),
  sourceRunId: z.string().min(1).nullable().optional(),
  sourceAttemptId: z.string().min(1).nullable().optional(),
  sourceArtifactId: z.string().min(1).nullable().optional(),
  capability: z.string().nullable().optional(),
  operation: z.string().nullable().optional(),
  resourceRef: z.string().nullable().optional(),
  payload: z.record(z.string(), z.unknown()).default({}),
  expiresAtMs: z.coerce.number().int().positive().nullable().optional()
})

const resolveDesktopDispatchSchema = strictObject({
  dispatchId: z.string().min(1),
  ownerId: z.string().min(1).optional(),
  status: z.enum(['resolved', 'cancelled']),
  resolvedBy: z.string().nullable().optional(),
  resolution: z.record(z.string(), z.unknown()).default({}),
  grant: strictObject({
    sessionId: z.string().min(1).optional(),
    runId: z.string().min(1).nullable().optional(),
    capability: z.string().min(1),
    operation: z.string().min(1),
    resourcePattern: z.string().min(1),
    effect: z.enum(['allow', 'deny']).default('allow'),
    source: z.enum(['legacy_default', 'policy', 'user', 'system']).default('user'),
    constraintsJson: z.string().default('{}'),
    expiresAtMs: z.coerce.number().int().positive().nullable().optional()
  }).optional()
})

const cancelAgentRunSchema = strictObject({
  runId: z.string().min(1),
  ownerId: z.string().min(1).optional()
})

const inspectAgentArtifactsSchema = z
  .strictObject({
    artifactId: z.string().min(1).optional(),
    sessionId: z.string().min(1).optional(),
    runId: z.string().min(1).optional(),
    attemptId: z.string().min(1).optional(),
    ownerId: z.string().min(1).optional(),
    role: artifactRoleSchema.optional(),
    limit: z.coerce.number().int().positive().max(200).default(50)
  })
  .refine((value) => value.artifactId || value.sessionId || value.runId || value.attemptId, {
    message: 'Provide artifactId, sessionId, runId, or attemptId'
  })

const updateAgentArtifactLifecycleSchema = strictObject({
  artifactId: z.string().min(1),
  state: artifactLifecycleStateSchema,
  sessionId: z.string().min(1).optional(),
  runId: z.string().min(1).optional(),
  attemptId: z.string().min(1).optional(),
  ownerId: z.string().min(1).optional(),
  reason: z.string().min(1).max(500).optional(),
  metadata: z.record(z.string(), z.unknown()).default({})
})

const sendAgentMessageSchema = strictObject({
  sessionId: z.string().min(1),
  ownerId: z.string().min(1).optional(),
  prompt: z.string().min(1),
  mode: runModeSchema.default('ask'),
  adapterId: z.string().min(1).optional(),
  cwd: z.string().min(1).optional(),
  model: z.string().min(1).optional(),
  requestId: z.string().min(1).optional(),
  clientId: z.string().min(1).default('omi-control-tools'),
  metadata: z.record(z.string(), z.unknown()).default({})
})

const spawnBackgroundAgentSchema = strictObject({
  prompt: z.string().min(1),
  title: z.string().min(1).optional(),
  surfaceKind: z.string().min(1).default('floating_bar'),
  externalRefKind: z.string().min(1).optional(),
  externalRefId: z.string().min(1).optional(),
  ownerId: z.string().min(1).optional(),
  adapterId: z.string().min(1).optional(),
  defaultAdapterId: z.string().min(1).optional(),
  cwd: z.string().min(1).optional(),
  model: z.string().min(1).optional(),
  mode: runModeSchema.default('act'),
  requestId: z.string().min(1).optional(),
  clientId: z.string().min(1).default('omi-control-tools'),
  metadata: z.record(z.string(), z.unknown()).default({})
})

const spawnAgentSchema = strictObject({
  objective: z.string().min(1),
  provider: z.enum(['openclaw', 'hermes']).optional(),
  parentRunId: z.string().min(1).optional(),
  visible: z.boolean().default(true),
  title: z.string().min(1).optional(),
  externalRefId: z.string().min(1).optional(),
  ownerId: z.string().min(1).optional(),
  adapterId: z.string().min(1).optional(),
  cwd: z.string().min(1).optional(),
  model: z.string().min(1).optional(),
  requestId: z.string().min(1).optional(),
  clientId: z.string().min(1).default('omi-control-tools'),
  metadata: z.record(z.string(), z.unknown()).default({})
})

const runAgentAndWaitSchema = strictObject({
  objective: z.string().min(1),
  parentRunId: z.string().min(1),
  context: z.string().max(4000).optional(),
  ownerId: z.string().min(1).optional(),
  adapterId: z.string().min(1).optional(),
  cwd: z.string().min(1).optional(),
  model: z.string().min(1).optional(),
  runMode: runModeSchema.default('ask'),
  requestId: z.string().min(1).optional(),
  clientId: z.string().min(1).default('omi-control-tools'),
  maxDepth: z.coerce.number().int().min(1).max(5).default(3),
  maxBudgetUsd: z.coerce.number().positive().max(10).default(5),
  metadata: z.record(z.string(), z.unknown()).default({})
})

const setDesktopAttentionOverrideSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  subjectKind: z.string().min(1),
  subjectId: z.string().min(1),
  dismissed: z.boolean().default(true),
  hiddenUntilMs: z.coerce.number().int().positive().nullable().optional(),
  reason: z.string().min(1).optional()
})

export const agentControlToolSchemas = {
  list_agent_sessions: listAgentSessionsSchema,
  get_agent_run: getAgentRunSchema,
  build_desktop_awareness_snapshot: buildDesktopAwarenessSnapshotSchema,
  list_desktop_action_queue: listDesktopActionQueueSchema,
  get_desktop_open_loops: getDesktopOpenLoopsSchema,
  build_desktop_context_packet: buildDesktopContextPacketSchema,
  route_desktop_intent: routeDesktopIntentSchema,
  evaluate_desktop_tool_policy: evaluateDesktopToolPolicySchema,
  create_desktop_dispatch: createDesktopDispatchSchema,
  resolve_desktop_dispatch: resolveDesktopDispatchSchema,
  cancel_agent_run: cancelAgentRunSchema,
  inspect_agent_artifacts: inspectAgentArtifactsSchema,
  update_agent_artifact_lifecycle: updateAgentArtifactLifecycleSchema,
  send_agent_message: sendAgentMessageSchema,
  spawn_background_agent: spawnBackgroundAgentSchema,
  spawn_agent: spawnAgentSchema,
  run_agent_and_wait: runAgentAndWaitSchema,
  set_desktop_attention_override: setDesktopAttentionOverrideSchema
} as const

export type AgentControlToolName = keyof typeof agentControlToolSchemas

export const AGENT_CONTROL_TOOL_NAMES = agentControlCapabilityManifest.map(
  (tool) => tool.name
) as AgentControlToolName[]

const CONTROL_TOOL_NAME_SET = new Set<string>(Object.keys(agentControlToolSchemas))

/**
 * Tools that are never advertised to a model-facing surface, only reachable
 * through trusted direct control:
 *   - `spawn_background_agent` — host coordinator entrypoint (`surfaces: []`).
 *     Unrestricted background-spawn rights: `backgroundSpawnAuthority` hands the
 *     kernel `trustedUserSpawn` for any non-leaf caller that omits a
 *     `callerSessionId`.
 *   - `resolve_desktop_dispatch` — resolving a dispatch IS the user's consent;
 *     a model may never grant itself one.
 *
 * Not being advertised is not a gate — a caller can still name a tool it was
 * never shown. Every name in this set is therefore ALSO rejected at runtime in
 * `handleAgentControlToolCall` when the caller is not trusted direct control,
 * which makes the set self-enforcing: adding a name here gates it everywhere.
 *
 * DELIBERATE DEVIATION FROM macOS. The Mac original advertises-but-does-not-gate
 * `spawn_background_agent` (control-tools.ts:555-583, 906-916) — a model-facing
 * coordinator there can call it by name. Windows is stricter on purpose. Do not
 * "restore parity" by removing this gate.
 */
export const TRUSTED_DIRECT_CONTROL_ONLY_TOOL_NAMES = new Set<string>([
  'resolve_desktop_dispatch',
  'spawn_background_agent'
])

export interface AgentControlToolDefinition {
  name: AgentControlToolName
  description: string
  inputSchema: Record<string, unknown>
}

export const agentControlToolDefinitions: AgentControlToolDefinition[] =
  agentControlCapabilityManifest.map((tool) => ({
    name: tool.name,
    description: tool.description,
    inputSchema: agentControlInputSchema(tool)
  }))

/**
 * The tool definitions a given caller may see. Belt-and-suspenders with the
 * handler-level assertions: a leaf worker is not even shown the tools it would
 * be rejected for calling, and a model-facing surface is never shown the
 * trusted-direct-control-only tools.
 */
export function agentControlToolDefinitionsFor(input: {
  executionRole?: AgentExecutionRole
  trustedUserControl?: boolean
  surface?: 'desktopChat' | 'realtimeHub'
}): AgentControlToolDefinition[] {
  const role = input.executionRole ?? 'coordinator'
  return agentControlToolDefinitions.filter((definition) => {
    const tool = agentControlCapabilityManifest.find((entry) => entry.name === definition.name)
    if (!tool) return false
    if (!input.trustedUserControl && TRUSTED_DIRECT_CONTROL_ONLY_TOOL_NAMES.has(definition.name)) {
      return false
    }
    if (!executionRoleAllowsToolName(role, definition.name)) return false
    // `spawn_background_agent` declares `allowedSurfaces: []` — it is never
    // advertised to any surface.
    const allowedSurfaces: readonly string[] = tool.allowedSurfaces
    if (input.surface && !allowedSurfaces.includes(input.surface)) return false
    return true
  })
}

function executionRoleAllowsToolName(role: AgentExecutionRole, name: string): boolean {
  try {
    assertLeafControlToolsAllowed({ executionRole: role }, name)
    return true
  } catch {
    return false
  }
}

export interface AgentControlToolContext {
  kernel: AgentRuntimeKernel
  /**
   * The adapter selected by the owning desktop surface. New background work must
   * inherit this route rather than silently selecting a local provider.
   */
  defaultAdapterId?: string
  /** Kernel-owned provider and role policy for the active control caller. */
  providerBoundary?: ProviderBoundary
  executionRole?: AgentExecutionRole
  /** Persisted caller session used for kernel-level spawn authority checks. */
  callerSessionId?: string
  /** @deprecated Compatibility for older direct callers; use executionRole. */
  canSpawnAgents?: boolean
  trustedUserControl?: boolean
  getOwnerId?: () => string
  recoverRunInput?: (
    adapterId: string
  ) => Pick<ExecuteAgentRunInput, 'maxAttempts' | 'recoverAfterError'>
}

function controlRunRecovery(
  context: AgentControlToolContext,
  adapterId: string
): Pick<ExecuteAgentRunInput, 'maxAttempts' | 'recoverAfterError'> {
  return context.recoverRunInput?.(adapterId) ?? {}
}

function defaultControlAdapterId(context: AgentControlToolContext): string {
  return context.defaultAdapterId ?? 'acp'
}

function assertAdapterAllowedForControlRun(
  context: AgentControlToolContext,
  adapterId: string
): void {
  if (!context.defaultAdapterId && !context.providerBoundary) {
    return
  }
  const owningAdapterId = defaultControlAdapterId(context)
  resolveAdapterWithinBoundary({
    providerBoundary: context.providerBoundary ?? providerBoundaryForAdapter(owningAdapterId),
    defaultAdapterId: owningAdapterId,
    requestedAdapterId: adapterId
  })
}

/**
 * A signed desktop action, or the explicit `provider` selector on the canonical
 * top-level spawn_agent tool, may start a new local-provider session. The active
 * bridge can still be a managed-cloud adapter because it is only carrying the
 * control RPC; it is not the owner of the new session's credentials.
 *
 * An adapterId alone does not get this exception, and neither does any
 * parent-linked delegation. Those must stay inside the caller's persisted
 * provider boundary.
 */
function assertAdapterAllowedForTopLevelLocalProviderSpawn(
  context: AgentControlToolContext,
  adapterId: string,
  directedProvider?: 'hermes' | 'openclaw'
): void {
  const hasDirectedLocalProvider = directedProvider === adapterId
  if (!context.trustedUserControl && !hasDirectedLocalProvider) {
    assertAdapterAllowedForControlRun(context, adapterId)
    return
  }
  if (!isProductionAdapterId(adapterId)) {
    throw new Error(`Unknown production adapter: ${adapterId}`)
  }
  resolveAdapterWithinBoundary({
    providerBoundary: providerBoundaryForAdapter(adapterId),
    defaultAdapterId: adapterId,
    requestedAdapterId: adapterId
  })
}

/**
 * Signed direct control resumes the target session's persisted boundary. This
 * keeps a user-selected local-provider session usable while the coordinator
 * bridge itself is using managed cloud routing, and still prevents adapter
 * changes on either local or managed sessions.
 */
function assertAdapterAllowedForDirectSessionContinuation(
  context: AgentControlToolContext,
  adapterId: string,
  targetPolicy: Pick<AgentSession, 'providerBoundary' | 'defaultAdapterId'>
): void {
  if (!context.trustedUserControl) {
    assertAdapterAllowedForControlRun(context, adapterId)
    return
  }
  resolveAdapterWithinBoundary({
    providerBoundary: targetPolicy.providerBoundary,
    defaultAdapterId: targetPolicy.defaultAdapterId,
    requestedAdapterId: adapterId
  })
}

function backgroundSpawnAuthority(context: AgentControlToolContext): {
  callerSessionId?: string
  trustedUserSpawn?: boolean
} {
  if (context.callerSessionId) {
    return { callerSessionId: context.callerSessionId }
  }
  if (context.trustedUserControl === true || context.executionRole !== 'leaf') {
    return { trustedUserSpawn: true }
  }
  return {}
}

export const DEFAULT_LOCAL_OWNER_ID = 'desktop-local-user'

export function isAgentControlToolName(name: string): name is AgentControlToolName {
  return CONTROL_TOOL_NAME_SET.has(name)
}

export async function handleAgentControlToolCall(
  context: AgentControlToolContext,
  name: string,
  input: Record<string, unknown>
): Promise<string> {
  if (!isAgentControlToolName(name)) {
    return JSON.stringify({
      ok: false,
      error: {
        code: 'unknown_control_tool',
        message: `Unknown control tool: ${name}`
      }
    })
  }
  try {
    // INV-AGENT leaf-role guard. Runs before ANY tool executes, on every call.
    // Kept ahead of the trusted-control gate below so that a leaf caller of a
    // tool covered by BOTH is still rejected by this one — each guard keeps its
    // own failing test.
    assertLeafControlToolsAllowed(context, name)

    // Trusted-direct-control gate — still before parsing and before any kernel
    // call. Covers EVERY name in TRUSTED_DIRECT_CONTROL_ONLY_TOOL_NAMES: being
    // absent from a caller's advertised tool list does not stop it from naming
    // the tool anyway.
    if (TRUSTED_DIRECT_CONTROL_ONLY_TOOL_NAMES.has(name) && !context.trustedUserControl) {
      return JSON.stringify({
        ok: false,
        error: {
          code: 'policy_denied',
          message: `${name} requires trusted user control`
        }
      })
    }

    switch (name) {
      case 'list_agent_sessions': {
        const parsed = agentControlToolSchemas.list_agent_sessions.parse(input)
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId)
        const sessions = context.kernel.listSessions({ ...parsed, ownerId })
        const overrides = context.kernel.listDesktopAttentionOverrides(ownerId)
        return stringifyToolResult(serializeAgentSessionsList(sessions, overrides))
      }
      case 'get_agent_run': {
        const parsed = agentControlToolSchemas.get_agent_run.parse(input)
        const details = context.kernel.getRun({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId)
        })
        return stringifyToolResult(serializeRunDetails(details))
      }
      case 'build_desktop_awareness_snapshot': {
        const parsed = agentControlToolSchemas.build_desktop_awareness_snapshot.parse(input)
        const snapshot = context.kernel.buildDesktopAwarenessSnapshot({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId)
        })
        return stringifyToolResult({ snapshot: serializeAwarenessSnapshot(snapshot) })
      }
      case 'list_desktop_action_queue': {
        const parsed = agentControlToolSchemas.list_desktop_action_queue.parse(input)
        const actionQueue = context.kernel.listDesktopActionQueue({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId)
        })
        return stringifyToolResult({ actionQueue })
      }
      case 'get_desktop_open_loops': {
        const parsed = agentControlToolSchemas.get_desktop_open_loops.parse(input)
        const openLoops = context.kernel.getDesktopOpenLoops({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId)
        })
        return stringifyToolResult({ openLoops })
      }
      case 'build_desktop_context_packet': {
        const parsed = agentControlToolSchemas.build_desktop_context_packet.parse(input)
        const built = context.kernel.persistDesktopContextPacket({
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
          sessionId: parsed.sessionId ?? null,
          runId: parsed.runId ?? null,
          surfaceKind: parsed.surfaceKind,
          objective: parsed.objective,
          snippets: parsed.packetJson.snippets,
          selectedToolBundles: parsed.packetJson.selectedToolBundles,
          constraints: parsed.packetJson.constraints,
          evidenceRequired: parsed.packetJson.evidenceRequired,
          boundaryPolicy: parsed.packetJson.boundaryPolicy,
          ttlMs: parsed.ttlMs,
          retentionClass: parsed.retentionClass
        })
        return stringifyToolResult({
          packet: {
            ...built.packet,
            packetJson: built.packet.packetJson,
            redactedPreviewJson: built.packet.redactedPreviewJson
          },
          accessLogs: built.accessLogs
        })
      }
      case 'route_desktop_intent': {
        const parsed = agentControlToolSchemas.route_desktop_intent.parse(input)
        const route = context.kernel.routeDesktopIntent({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
          taskId: parsed.taskId ?? null
        })
        return stringifyToolResult({ route })
      }
      case 'evaluate_desktop_tool_policy': {
        const parsed = agentControlToolSchemas.evaluate_desktop_tool_policy.parse(input)
        const policy = evaluateDesktopToolPolicy({
          ...parsed,
          selectedBundles: parsed.selectedBundles as DesktopCoordinatorBundle[],
          requestedBundles: parsed.requestedBundles as DesktopCoordinatorBundle[] | undefined
        })
        return stringifyToolResult({ policy })
      }
      case 'create_desktop_dispatch': {
        const parsed = agentControlToolSchemas.create_desktop_dispatch.parse(input)
        const dispatch = context.kernel.createDesktopDispatch({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
          payloadJson: JSON.stringify(parsed.payload)
        })
        return stringifyToolResult({ dispatch })
      }
      case 'resolve_desktop_dispatch': {
        const parsed = agentControlToolSchemas.resolve_desktop_dispatch.parse(input)
        const result = context.kernel.resolveDesktopDispatch(parsed.dispatchId, {
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
          status: parsed.status,
          resolvedBy: parsed.resolvedBy ?? 'user',
          resolutionJson: JSON.stringify(parsed.resolution),
          grant: parsed.grant
        })
        return stringifyToolResult({
          dispatch: result.dispatch,
          grant: result.grant,
          event: result.event ? serializeEvent(result.event) : null
        })
      }
      case 'cancel_agent_run': {
        const parsed = agentControlToolSchemas.cancel_agent_run.parse(input)
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId)
        const cancellation = await context.kernel.cancelRun(parsed.runId, { ownerId })
        const details = context.kernel.getRun({
          runId: parsed.runId,
          ownerId,
          includeEvents: true,
          eventLimit: 100
        })
        return stringifyToolResult({
          cancellation,
          run: serializeRun(details.run),
          attempts: details.attempts.map(serializeAttempt)
        })
      }
      case 'inspect_agent_artifacts': {
        const parsed = agentControlToolSchemas.inspect_agent_artifacts.parse(input)
        const artifacts = context.kernel.inspectArtifacts({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId)
        })
        return stringifyToolResult({ artifacts: artifacts.map(serializeArtifact) })
      }
      case 'update_agent_artifact_lifecycle': {
        const parsed = agentControlToolSchemas.update_agent_artifact_lifecycle.parse(input)
        const result = context.kernel.updateArtifactLifecycle({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId)
        })
        return stringifyToolResult({
          artifact: serializeArtifact(result.artifact),
          changed: result.changed,
          event: result.event ? serializeEvent(result.event) : null
        })
      }
      case 'send_agent_message': {
        const parsed = agentControlToolSchemas.send_agent_message.parse(input)
        const targetPolicy = context.kernel.executionPolicyForSession(parsed.sessionId)
        const adapterId = parsed.adapterId ?? targetPolicy.defaultAdapterId
        assertAdapterAllowedForDirectSessionContinuation(context, adapterId, targetPolicy)
        rejectSynchronousNestedRun(context, adapterId, parsed.sessionId)
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId)
        const requestId =
          parsed.requestId ?? `send-${Date.now()}-${Math.random().toString(16).slice(2)}`
        const result = await context.kernel.sendAgentMessage({
          ...parsed,
          ...controlRunRecovery(context, adapterId),
          ownerId,
          requestId,
          metadata: { ...(parsed.metadata ?? {}) }
        })
        return stringifyToolResult({
          session: serializeSession(result.session),
          run: serializeRun(result.run),
          attempt: serializeAttempt(result.attempt),
          adapterSessionId: result.adapterSessionId,
          terminalStatus: result.terminalStatus,
          text: result.text,
          artifacts: result.artifacts.map(serializeArtifact)
        })
      }
      case 'spawn_background_agent': {
        assertAgentSpawningAllowed(context)
        const parsed = agentControlToolSchemas.spawn_background_agent.parse(input)
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId)
        const requestId =
          parsed.requestId ?? `background-${Date.now()}-${Math.random().toString(16).slice(2)}`
        const adapterId =
          parsed.adapterId ?? parsed.defaultAdapterId ?? defaultControlAdapterId(context)
        assertAdapterAllowedForTopLevelLocalProviderSpawn(context, adapterId)
        const result = await context.kernel.spawnBackgroundAgent({
          ...parsed,
          ...controlRunRecovery(context, adapterId),
          ...backgroundSpawnAuthority(context),
          adapterId,
          defaultAdapterId: adapterId,
          ownerId,
          requestId,
          surfaceKind: parsed.surfaceKind ?? 'floating_bar',
          metadata: { ...(parsed.metadata ?? {}) }
        })
        return stringifyToolResult({
          session: serializeSession(result.session),
          run: serializeRun(result.run),
          attempt: result.attempt ? serializeAttempt(result.attempt) : null
        })
      }
      case 'spawn_agent': {
        assertAgentSpawningAllowed(context)
        const parsed = agentControlToolSchemas.spawn_agent.parse(input)
        if (parsed.parentRunId) {
          assertCanonicalRunId(parsed.parentRunId, 'parentRunId')
        }
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId)
        const requestId =
          parsed.requestId ?? `spawn-agent-${Date.now()}-${Math.random().toString(16).slice(2)}`
        if (parsed.provider && parsed.adapterId && parsed.provider !== parsed.adapterId) {
          throw new Error('provider and adapterId must match when both are supplied')
        }
        const adapterId =
          parsed.adapterId ??
          (parsed.provider === 'openclaw'
            ? 'openclaw'
            : parsed.provider === 'hermes'
              ? 'hermes'
              : undefined) ??
          (parsed.parentRunId
            ? context.kernel.defaultAdapterIdForRun(parsed.parentRunId)
            : defaultControlAdapterId(context))
        if (parsed.parentRunId) {
          assertAdapterAllowedForControlRun(context, adapterId)
        } else {
          assertAdapterAllowedForTopLevelLocalProviderSpawn(context, adapterId, parsed.provider)
        }
        const visiblePillExternalRefId = parsed.visible
          ? (parsed.externalRefId ?? randomUUID())
          : parsed.externalRefId
        const childSurfaceKind = parsed.visible ? 'floating_bar' : 'delegated_agent'
        const childExternalRefKind = parsed.visible ? 'pill' : undefined
        if (parsed.parentRunId) {
          const result = await context.kernel.delegateAgent({
            ...controlRunRecovery(context, adapterId),
            mode: 'spawn',
            parentRunId: parsed.parentRunId,
            objective: parsed.objective,
            ownerId,
            requestId,
            adapterId,
            defaultAdapterId: adapterId,
            childSurfaceKind,
            childExternalRefKind,
            childExternalRefId: visiblePillExternalRefId,
            childTitle: parsed.title ?? `Delegated: ${parsed.objective.slice(0, 80)}`,
            cwd: parsed.cwd,
            model: parsed.model,
            runMode: 'act',
            clientId: parsed.clientId,
            metadata: { ...(parsed.metadata ?? {}), visible: parsed.visible }
          })
          return stringifyToolResult({
            delegation: serializeDelegation(result.delegation),
            session: serializeSession(result.childSession),
            run: serializeRun(result.childRun),
            attempt: result.childAttempt ? serializeAttempt(result.childAttempt) : null
          })
        }
        const result = await context.kernel.spawnBackgroundAgent({
          ...controlRunRecovery(context, adapterId),
          ...backgroundSpawnAuthority(context),
          ownerId,
          clientId: parsed.clientId,
          requestId,
          prompt: parsed.objective,
          title: parsed.title ?? `Background: ${parsed.objective.slice(0, 80)}`,
          surfaceKind: childSurfaceKind,
          externalRefKind: childExternalRefKind,
          externalRefId: visiblePillExternalRefId,
          adapterId,
          defaultAdapterId: adapterId,
          cwd: parsed.cwd,
          model: parsed.model,
          mode: 'act',
          metadata: {
            ...(parsed.metadata ?? {}),
            visible: parsed.visible,
            provider: parsed.provider ?? null
          }
        })
        return stringifyToolResult({
          session: serializeSession(result.session),
          run: serializeRun(result.run),
          attempt: result.attempt ? serializeAttempt(result.attempt) : null
        })
      }
      case 'run_agent_and_wait': {
        assertAgentSpawningAllowed(context)
        const parsed = agentControlToolSchemas.run_agent_and_wait.parse(input)
        assertCanonicalRunId(parsed.parentRunId, 'parentRunId')
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId)
        const requestId =
          parsed.requestId ?? `run-and-wait-${Date.now()}-${Math.random().toString(16).slice(2)}`
        const adapterId =
          parsed.adapterId ?? context.kernel.defaultAdapterIdForRun(parsed.parentRunId)
        assertAdapterAllowedForControlRun(context, adapterId)
        const result = await context.kernel.delegateAgent({
          ...controlRunRecovery(context, adapterId),
          mode: 'call',
          parentRunId: parsed.parentRunId,
          objective: parsed.objective,
          context: parsed.context,
          ownerId,
          requestId,
          adapterId,
          defaultAdapterId: adapterId,
          cwd: parsed.cwd,
          model: parsed.model,
          runMode: parsed.runMode,
          clientId: parsed.clientId,
          maxDepth: parsed.maxDepth,
          maxBudgetUsd: parsed.maxBudgetUsd,
          metadata: { ...(parsed.metadata ?? {}) }
        })
        return stringifyToolResult({
          delegation: serializeDelegation(result.delegation),
          session: serializeSession(result.childSession),
          run: serializeRun(result.childRun),
          attempt: result.childAttempt ? serializeAttempt(result.childAttempt) : null,
          adapterSessionId: result.adapterSessionId ?? null,
          terminalStatus: result.terminalStatus ?? null,
          result: result.result
            ? { ...result.result, artifacts: result.result.artifacts.map(serializeArtifact) }
            : null
        })
      }
      case 'set_desktop_attention_override': {
        const parsed = agentControlToolSchemas.set_desktop_attention_override.parse(input)
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId)
        const override = context.kernel.setDesktopAttentionOverride({
          ownerId,
          subjectKind: parsed.subjectKind,
          subjectId: parsed.subjectId,
          dismissedAtMs: parsed.dismissed ? Date.now() : null,
          hiddenUntilMs: parsed.hiddenUntilMs ?? null,
          reason: parsed.reason ?? null
        })
        return stringifyToolResult({ override })
      }
    }
  } catch (error) {
    return JSON.stringify({
      ok: false,
      error: {
        code: error instanceof z.ZodError ? 'invalid_tool_input' : 'control_tool_failed',
        message: error instanceof Error ? error.message : String(error)
      }
    })
  }
}

function assertCanonicalRunId(value: string, fieldName: string): void {
  if (!value.startsWith('run_')) {
    throw new Error(
      `${fieldName} must be a canonical Omi run_id starting with "run_"; omit it for a top-level background agent`
    )
  }
}

function controlToolOwnerId(context: AgentControlToolContext): string {
  const ownerId = context.getOwnerId?.().trim()
  return ownerId || DEFAULT_LOCAL_OWNER_ID
}

function effectiveControlToolOwnerId(
  context: AgentControlToolContext,
  requestedOwnerId?: string
): string {
  const activeOwnerId = controlToolOwnerId(context)
  const ownerGuard = requestedOwnerId?.trim()
  if (requestedOwnerId !== undefined && !ownerGuard) {
    throw new Error('Requested ownerId cannot be empty')
  }
  if (ownerGuard && ownerGuard !== activeOwnerId) {
    throw new Error('Requested ownerId does not match the active control owner')
  }
  return activeOwnerId
}

function rejectSynchronousNestedRun(
  context: AgentControlToolContext,
  adapterId: string,
  sessionId?: string
): void {
  if (!context.kernel.isAdapterRegistered(adapterId)) {
    return
  }
  if (
    (sessionId && context.kernel.hasActiveExecutionForSessionAdapter(sessionId, adapterId)) ||
    !context.kernel.hasExecutionCapacityForAdapter(adapterId)
  ) {
    throw new Error(
      `Synchronous ${adapterId} control-tool runs are unavailable while that adapter is already executing; use spawn mode or retry after the current run finishes.`
    )
  }
}

function stringifyToolResult(payload: Record<string, unknown>): string {
  return JSON.stringify({ ok: true, ...payload })
}

// === Entity serializers ======================================================

export function serializeArtifact(artifact: AgentArtifact): Record<string, unknown> {
  return {
    artifactId: artifact.artifactId,
    sessionId: artifact.sessionId,
    runId: artifact.runId,
    attemptId: artifact.attemptId,
    kind: artifact.kind,
    role: artifact.role,
    uri: artifact.uri,
    displayName: artifact.displayName,
    mimeType: artifact.mimeType,
    contentHash: artifact.contentHash,
    sizeBytes: artifact.sizeBytes,
    lifecycleState: artifact.lifecycleState,
    lifecycleUpdatedAtMs: artifact.lifecycleUpdatedAtMs,
    metadata: parseJsonObject(artifact.metadataJson),
    createdAtMs: artifact.createdAtMs
  }
}

function serializeAgentSessionsList(
  sessions: Parameters<typeof serializeSessionSummary>[0][],
  overrides: {
    subjectKind: string
    subjectId: string
    dismissedAtMs?: number | null
    hiddenUntilMs?: number | null
  }[]
): Record<string, unknown> {
  const dismissed = new Set(
    overrides
      .filter(
        (override) => override.dismissedAtMs != null || (override.hiddenUntilMs ?? 0) > Date.now()
      )
      .map((override) => `${override.subjectKind}:${override.subjectId}`)
  )
  const summaries = sessions.map(serializeSessionSummary)
  const floatingAgentPills = summaries
    .filter((summary) => {
      const session = summary.session as Record<string, unknown>
      const surfaceKind = session.surfaceKind
      if (
        surfaceKind !== 'floating_bar' &&
        surfaceKind !== 'background_agent' &&
        surfaceKind !== 'floating_pill'
      ) {
        return false
      }
      const run = (summary.activeRun ?? summary.latestRun) as Record<string, unknown> | null
      const runId = typeof run?.runId === 'string' ? run.runId : null
      if (runId && dismissed.has(`run:${runId}`)) return false
      const sessionId = typeof session.sessionId === 'string' ? session.sessionId : null
      if (sessionId && dismissed.has(`session:${sessionId}`)) return false
      return true
    })
    .map((summary) => serializeFloatingPillSnapshot(summary))
  const taskAgents = summaries
    .filter((summary) => (summary.session as Record<string, unknown>).surfaceKind === 'task_chat')
    .map((summary) => serializeTaskAgentSnapshot(summary))
  return {
    sessions: summaries,
    task_agents: taskAgents,
    floating_agent_pills: floatingAgentPills
  }
}

function serializeFloatingPillSnapshot(summary: Record<string, unknown>): Record<string, unknown> {
  const session = summary.session as Record<string, unknown>
  const run = (summary.activeRun ?? summary.latestRun) as Record<string, unknown> | null
  const input = (run?.input as Record<string, unknown> | undefined) ?? {}
  const metadata = (session.metadata as Record<string, unknown> | undefined) ?? {}
  const runId = typeof run?.runId === 'string' && run.runId ? run.runId : null
  const sessionId =
    typeof session.sessionId === 'string' && session.sessionId ? session.sessionId : null
  const errorMessage =
    typeof run?.errorMessage === 'string' && run.errorMessage ? run.errorMessage : null
  const errorCode = typeof run?.errorCode === 'string' && run.errorCode ? run.errorCode : null
  const pillId =
    (typeof session.externalRefId === 'string' && session.externalRefId) ||
    (typeof metadata.pillId === 'string' && metadata.pillId) ||
    runId ||
    sessionId
  return {
    id: pillId,
    runId,
    sessionId,
    title: session.title ?? 'Background agent',
    status: run?.status ?? session.status ?? 'unknown',
    latestActivity: run?.finalText ?? errorMessage ?? input.prompt ?? session.title ?? '',
    query: typeof input.prompt === 'string' ? input.prompt : '',
    createdAtMs: session.createdAtMs ?? null,
    completedAtMs: run?.completedAtMs ?? null,
    provider: metadata.provider ?? null,
    errorCode,
    errorMessage
  }
}

function serializeTaskAgentSnapshot(summary: Record<string, unknown>): Record<string, unknown> {
  const session = summary.session as Record<string, unknown>
  const run = (summary.activeRun ?? summary.latestRun) as Record<string, unknown> | null
  return {
    taskId: session.externalRefId ?? null,
    sessionId: session.sessionId ?? null,
    runId: run?.runId ?? null,
    title: session.title ?? null,
    status: run?.status ?? session.status ?? 'unknown',
    statusText: run?.finalText ?? null,
    lastError: run?.errorMessage ?? null,
    updatedAtMs: run?.updatedAtMs ?? session.updatedAtMs ?? null
  }
}

function serializeSessionSummary(summary: {
  session: AgentSession
  latestRun?: AgentRun
  activeRun?: AgentRun
  adapterBindings: AdapterBinding[]
}): Record<string, unknown> {
  return {
    session: serializeSession(summary.session),
    latestRun: summary.latestRun ? serializeRun(summary.latestRun) : null,
    activeRun: summary.activeRun ? serializeRun(summary.activeRun) : null,
    adapterBindings: summary.adapterBindings.map(serializeBinding)
  }
}

function serializeRunDetails(details: {
  session: AgentSession
  run: AgentRun
  attempts: RunAttempt[]
  adapterBindings: AdapterBinding[]
  artifacts: AgentArtifact[]
  events: AgentEvent[]
  parentDelegations: AgentDelegation[]
  childDelegations: AgentDelegation[]
}): Record<string, unknown> {
  return {
    session: serializeSession(details.session),
    run: serializeRun(details.run),
    attempts: details.attempts.map(serializeAttempt),
    adapterBindings: details.adapterBindings.map(serializeBinding),
    artifacts: details.artifacts.map(serializeArtifact),
    events: details.events.map(serializeEvent),
    parentDelegations: details.parentDelegations.map(serializeDelegation),
    childDelegations: details.childDelegations.map(serializeDelegation)
  }
}

function serializeAwarenessSnapshot(snapshot: DesktopAwarenessSnapshot): Record<string, unknown> {
  return {
    ownerId: snapshot.ownerId,
    generatedAtMs: snapshot.generatedAtMs,
    sessions: snapshot.sessions.map(serializeSessionSummary),
    runs: snapshot.runs.map(serializeRun),
    dispatches: snapshot.dispatches,
    artifactDeliveries: snapshot.artifactDeliveries,
    memoryCandidates: snapshot.memoryCandidates,
    taskCandidates: snapshot.taskCandidates,
    actionQueue: snapshot.actionQueue,
    runtime: snapshot.runtime
  }
}

function serializeSession(session: AgentSession): Record<string, unknown> {
  return {
    sessionId: session.sessionId,
    ownerId: session.ownerId,
    agentDefinitionId: session.agentDefinitionId,
    title: session.title,
    status: session.status,
    surfaceKind: session.surfaceKind,
    executionRole: session.executionRole,
    providerBoundary: session.providerBoundary,
    externalRefKind: session.externalRefKind,
    externalRefId: session.externalRefId,
    defaultAdapterId: session.defaultAdapterId,
    defaultCwd: session.defaultCwd,
    modelProfile: session.modelProfile,
    metadata: parseJsonObject(session.metadataJson),
    createdAtMs: session.createdAtMs,
    updatedAtMs: session.updatedAtMs,
    lastActivityAtMs: session.lastActivityAtMs
  }
}

/**
 * Error fields are appended only when non-empty — a healthy entity must not
 * carry `errorCode: null` / `errorMessage: null` noise into a model's context.
 */
function appendErrorFields(
  payload: Record<string, unknown>,
  errorCode: string | null | undefined,
  errorMessage: string | null | undefined
): Record<string, unknown> {
  if (errorCode != null && errorCode !== '') {
    payload.errorCode = errorCode
  }
  if (errorMessage != null && errorMessage !== '') {
    payload.errorMessage = errorMessage
  }
  return payload
}

function serializeRun(run: AgentRun): Record<string, unknown> {
  return appendErrorFields(
    {
      runId: run.runId,
      sessionId: run.sessionId,
      parentRunId: run.parentRunId,
      clientId: run.clientId,
      requestId: run.requestId,
      idempotencyKey: run.idempotencyKey,
      status: run.status,
      mode: run.mode,
      input: parseJsonObject(run.inputJson),
      requestedModelId: run.requestedModelId,
      cwd: run.cwd,
      finalText: run.finalText,
      result: parseOptionalJsonObject(run.resultJson),
      usage: {
        inputTokens: run.inputTokens,
        outputTokens: run.outputTokens,
        cacheReadTokens: run.cacheReadTokens,
        cacheWriteTokens: run.cacheWriteTokens,
        costUsd: run.costUsd
      },
      createdAtMs: run.createdAtMs,
      startedAtMs: run.startedAtMs,
      completedAtMs: run.completedAtMs,
      updatedAtMs: run.updatedAtMs
    },
    run.errorCode,
    run.errorMessage
  )
}

function serializeAttempt(attempt: RunAttempt): Record<string, unknown> {
  return appendErrorFields(
    {
      attemptId: attempt.attemptId,
      runId: attempt.runId,
      attemptNo: attempt.attemptNo,
      status: attempt.status,
      adapterId: attempt.adapterId,
      runtimeNodeId: attempt.runtimeNodeId,
      bindingId: attempt.bindingId,
      adapterNativeRunId: attempt.adapterNativeRunId,
      resumeFromAttemptId: attempt.resumeFromAttemptId,
      checkpointArtifactId: attempt.checkpointArtifactId,
      retryReason: attempt.retryReason,
      retryable: attempt.retryable === 1,
      cancellationRequestedAtMs: attempt.cancellationRequestedAtMs,
      cancellationDispatchedAtMs: attempt.cancellationDispatchedAtMs,
      cancellationAcknowledgedAtMs: attempt.cancellationAcknowledgedAtMs,
      metadata: parseJsonObject(attempt.metadataJson),
      createdAtMs: attempt.createdAtMs,
      startedAtMs: attempt.startedAtMs,
      completedAtMs: attempt.completedAtMs,
      updatedAtMs: attempt.updatedAtMs
    },
    attempt.errorCode,
    attempt.errorMessage
  )
}

function serializeBinding(binding: AdapterBinding): Record<string, unknown> {
  return {
    bindingId: binding.bindingId,
    sessionId: binding.sessionId,
    adapterId: binding.adapterId,
    bindingGeneration: binding.bindingGeneration,
    adapterNativeSessionId: binding.adapterNativeSessionId,
    adapterInstanceId: binding.adapterInstanceId,
    resumeFidelity: binding.resumeFidelity,
    status: binding.status,
    cwd: binding.cwd,
    modelId: binding.modelId,
    metadata: parseJsonObject(binding.metadataJson),
    createdAtMs: binding.createdAtMs,
    updatedAtMs: binding.updatedAtMs,
    lastUsedAtMs: binding.lastUsedAtMs,
    invalidatedAtMs: binding.invalidatedAtMs
  }
}

function serializeEvent(event: AgentEvent): Record<string, unknown> {
  return {
    eventSeq: event.eventSeq,
    eventId: event.eventId,
    sessionId: event.sessionId,
    runId: event.runId,
    attemptId: event.attemptId,
    type: event.type,
    retentionClass: event.retentionClass,
    visibility: event.visibility,
    payload: parseJsonObject(event.payloadJson),
    createdAtMs: event.createdAtMs
  }
}

function serializeDelegation(delegation: AgentDelegation): Record<string, unknown> {
  return {
    delegationId: delegation.delegationId,
    parentSessionId: delegation.parentSessionId,
    parentRunId: delegation.parentRunId,
    childSessionId: delegation.childSessionId,
    childRunId: delegation.childRunId,
    mode: delegation.mode,
    status: delegation.status,
    objective: delegation.objective,
    request: parseJsonObject(delegation.requestJson),
    resultArtifactId: delegation.resultArtifactId,
    createdAtMs: delegation.createdAtMs,
    completedAtMs: delegation.completedAtMs
  }
}

function parseOptionalJsonObject(value: string | null): unknown {
  return value === null ? null : parseJsonObject(value)
}

function parseJsonObject(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch {
    return { raw: value }
  }
}
