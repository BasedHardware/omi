import { createHash, randomUUID } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { z } from "zod";
import { isProductionAdapterId } from "../adapters/interface.js";
import type {
  AgentArtifact,
  AgentDelegation,
  AgentEvent,
  AgentRun,
  AgentSession,
  AdapterBinding,
  RunAttempt,
} from "./types.js";
import { AgentRuntimeKernel, type DesktopAwarenessSnapshot, type ExecuteAgentRunInput } from "./kernel.js";
import { serializeArtifact } from "./artifact-serialization.js";
import { agentControlCapabilityManifest, agentControlInputSchema } from "./control-tool-manifest.js";
import type { McpServerBuildContext } from "./jsonl-transport.js";
import {
  parseAgentSpawnProducerJournalDescriptor,
  type AgentSpawnProducerJournalDescriptor,
} from "./agent-spawn-journal.js";
import { evaluateDesktopToolPolicy } from "./desktop-tool-policy.js";
import type { DesktopCoordinatorBundle } from "./desktop-tool-policy.js";
import type {
  EvidenceRef,
  WorkstreamContinuationCheckpoint,
  WorkstreamProductContext,
} from "./workstream-continuity.js";
import {
  executionRoleAllowsTool,
  LEAF_AGENT_CONTROL_TOOLS,
  providerBoundaryForAdapter,
  resolveAdapterWithinBoundary,
  type AgentExecutionRole,
  type ProviderBoundary,
} from "./execution-policy.js";

const sessionStatusSchema = z.enum(["open", "archived", "closed"]);
const agentSurfaceKindSchema = z.enum([
  "main_chat",
  "task_chat",
  "realtime",
  "delegated_agent",
  "background_agent",
  "floating_bar",
  "floating_pill",
]);
const originSurfaceKindSchema = z.enum([
  "main_chat",
  "floating_bar",
  "realtime",
  "task_chat",
  "agent_control",
]);
const artifactRoleSchema = z.enum(["input", "result", "checkpoint", "tool_output", "log", "other"]);
const artifactLifecycleStateSchema = z.enum(["retained", "dismissed", "opened"]);
const runModeSchema = z.enum(["ask", "act"]);
const delegationModeSchema = z.enum(["call", "spawn", "continue"]);
const desktopCoordinatorBundleSchema = z.enum([
  "desktop.agent_control.read",
  "desktop.agent_control.manage",
  "desktop.context.local_read",
  "desktop.context.screen_summary",
  "desktop.context.screenshot_image",
  "desktop.tasks.readwrite",
  "desktop.artifacts.manage",
  "desktop.automation.read",
  "desktop.automation.act_dev_only",
  "external.write_prepare",
  "external.write_send",
]);
const strictObject = <T extends z.ZodRawShape>(shape: T) => z.object(shape).strict();

const listAgentSessionsSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  status: sessionStatusSchema.optional(),
  surfaceKind: agentSurfaceKindSchema.optional(),
  limit: z.coerce.number().int().positive().max(200).default(50),
  beforeUpdatedAtMs: z.coerce.number().int().positive().optional(),
});

const getAgentRunSchema = strictObject({
  runId: z.string().min(1),
  ownerId: z.string().min(1).optional(),
  includeEvents: z.boolean().default(true),
  eventLimit: z.coerce.number().int().positive().max(500).default(100),
});

const buildDesktopAwarenessSnapshotSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  limit: z.coerce.number().int().positive().max(200).default(50),
});

const listDesktopActionQueueSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  staleAfterMs: z.coerce.number().int().positive().optional(),
  limit: z.coerce.number().int().positive().max(200).default(50),
});

const getDesktopOpenLoopsSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  limit: z.coerce.number().int().positive().max(200).default(50),
});

const contextSnippetSchema = strictObject({
  snippetId: z.string().min(1),
  sourceKind: z.enum([
    "omi_db",
    "rewind_timeline",
    "screen_current",
    "screenshot_image",
    "local_agent_api",
    "automation_bridge",
    "chat_surface",
    "task_chat",
  ]),
  operation: z.string().min(1),
  provenance: z.record(z.string(), z.unknown()).default({}),
  content: z.string().optional(),
  redactedContent: z.string().optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
  sensitivityTier: z.string().min(1),
  policyDecision: z.enum(["allowed", "denied", "dispatch_created"]).optional(),
  dispatchId: z.string().min(1).nullable().optional(),
  selected: z.boolean().optional(),
  tokenEstimate: z.coerce.number().int().positive().optional(),
});

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
    boundaryPolicy: z.record(z.string(), z.unknown()).default({}),
  }),
  ttlMs: z.coerce.number().int().positive(),
  retentionClass: z.enum(["ephemeral", "debug", "core"]),
});

const desktopIntentSyntaxFactsSchema = strictObject({
  delegationNegated: z.boolean().optional(),
  explicitSessionId: z.string().min(1).nullable().optional(),
  explicitRunId: z.string().min(1).nullable().optional(),
  parentRunId: z.string().min(1).nullable().optional(),
  explicitProvider: z.string().min(1).nullable().optional(),
  requestedAgentCount: z.coerce.number().int().positive().nullable().optional(),
});

const desktopIntentProposalSchema = z.discriminatedUnion("intent", [
  strictObject({ intent: z.literal("answer_inline") }),
  strictObject({ intent: z.literal("spawn_agent") }),
  strictObject({ intent: z.literal("continue_run") }),
  strictObject({
    intent: z.literal("clarify"),
    missing: z.array(z.string().min(1)).max(10).optional(),
  }),
]);

const routeDesktopIntentSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  utterance: z.string().min(1),
  surfaceKind: z.string().min(1),
  taskId: z.string().min(1).nullable().optional(),
  snapshotVersion: z.string().min(1).optional(),
  syntaxFacts: desktopIntentSyntaxFactsSchema.optional(),
  proposal: desktopIntentProposalSchema.optional(),
});

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
  isDevBundle: z.boolean().optional(),
});

const createDesktopDispatchSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  kind: z.enum([
    "approval",
    "routing_choice",
    "failure_recovery",
    "artifact_review",
    "memory_candidate",
    "task_candidate",
    "external_draft",
    "screen_context",
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
  expiresAtMs: z.coerce.number().int().positive().nullable().optional(),
});

const resolveDesktopDispatchSchema = strictObject({
  dispatchId: z.string().min(1),
  ownerId: z.string().min(1).optional(),
  status: z.enum(["resolved", "cancelled"]),
  resolvedBy: z.string().nullable().optional(),
  resolution: z.record(z.string(), z.unknown()).default({}),
  grant: strictObject({
    sessionId: z.string().min(1).optional(),
    runId: z.string().min(1).nullable().optional(),
    capability: z.string().min(1),
    operation: z.string().min(1),
    resourcePattern: z.string().min(1),
    effect: z.enum(["allow", "deny"]).default("allow"),
    source: z.enum(["legacy_default", "policy", "user", "system"]).default("user"),
    constraintsJson: z.string().default("{}"),
    expiresAtMs: z.coerce.number().int().positive().nullable().optional(),
  }).optional(),
});

const cancelAgentRunSchema = strictObject({
  runId: z.string().min(1),
  ownerId: z.string().min(1).optional(),
});

const inspectAgentArtifactsSchema = z
  .strictObject({
    artifactId: z.string().min(1).optional(),
    sessionId: z.string().min(1).optional(),
    runId: z.string().min(1).optional(),
    attemptId: z.string().min(1).optional(),
    ownerId: z.string().min(1).optional(),
    role: artifactRoleSchema.optional(),
    limit: z.coerce.number().int().positive().max(200).default(50),
  })
  .refine((value) => value.artifactId || value.sessionId || value.runId || value.attemptId, {
    message: "Provide artifactId, sessionId, runId, or attemptId",
  });

const updateAgentArtifactLifecycleSchema = strictObject({
  artifactId: z.string().min(1),
  state: artifactLifecycleStateSchema,
  sessionId: z.string().min(1).optional(),
  runId: z.string().min(1).optional(),
  attemptId: z.string().min(1).optional(),
  ownerId: z.string().min(1).optional(),
  reason: z.string().min(1).max(500).optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
});

const sendAgentMessageSchema = strictObject({
  sessionId: z.string().min(1),
  originSurfaceKind: originSurfaceKindSchema,
  ownerId: z.string().min(1).optional(),
  prompt: z.string().min(1),
  mode: runModeSchema.default("ask"),
  adapterId: z.string().min(1).optional(),
  cwd: z.string().min(1).optional(),
  model: z.string().min(1).optional(),
  requestId: z.string().min(1).optional(),
  clientId: z.string().min(1).default("omi-control-tools"),
  metadata: z.record(z.string(), z.unknown()).default({}),
});

const spawnBackgroundAgentSchema = strictObject({
  prompt: z.string().min(1),
  originSurfaceKind: originSurfaceKindSchema,
  title: z.string().min(1).optional(),
  surfaceKind: z.string().min(1).default("floating_bar"),
  externalRefKind: z.string().min(1).optional(),
  externalRefId: z.string().min(1).optional(),
  ownerId: z.string().min(1).optional(),
  adapterId: z.string().min(1).optional(),
  defaultAdapterId: z.string().min(1).optional(),
  cwd: z.string().min(1).optional(),
  model: z.string().min(1).optional(),
  mode: runModeSchema.default("act"),
  requestId: z.string().min(1).optional(),
  clientId: z.string().min(1).default("omi-control-tools"),
  metadata: z.record(z.string(), z.unknown()).default({}),
});

const spawnAgentPublicShape = {
  objective: z.string().min(1),
  // Gemini's realtime tool contract advertises this optional pill summary.
  // Keep it in the canonical strict parser so a valid provider tool call does
  // not fail before the child-admission boundary.
  brief: z.string().min(1).optional(),
  requestedAgentCount: z.coerce.number().int().min(1).max(8).default(1),
  provider: z.enum(["openclaw", "hermes"]).optional(),
  parentRunId: z.string().min(1).optional(),
  visible: z.boolean().default(true),
  title: z.string().min(1).optional(),
  externalRefId: z.string().min(1).optional(),
  ownerId: z.string().min(1).optional(),
  adapterId: z.string().min(1).optional(),
  cwd: z.string().min(1).optional(),
  model: z.string().min(1).optional(),
  requestId: z.string().min(1).optional(),
  clientId: z.string().min(1).default("omi-control-tools"),
  metadata: z.record(z.string(), z.unknown()).default({}),
} as const;

const spawnAgentSchema = strictObject(spawnAgentPublicShape);

const authorizedSpawnAgentSchema = strictObject({
  ...spawnAgentPublicShape,
  originSurfaceKind: originSurfaceKindSchema,
});

const runAgentAndWaitSchema = strictObject({
  objective: z.string().min(1),
  parentRunId: z.string().min(1),
  originSurfaceKind: originSurfaceKindSchema,
  context: z.string().max(4000).optional(),
  ownerId: z.string().min(1).optional(),
  adapterId: z.string().min(1).optional(),
  cwd: z.string().min(1).optional(),
  model: z.string().min(1).optional(),
  runMode: runModeSchema.default("ask"),
  requestId: z.string().min(1).optional(),
  clientId: z.string().min(1).default("omi-control-tools"),
  maxDepth: z.coerce.number().int().min(1).max(5).default(3),
  maxBudgetUsd: z.coerce.number().positive().max(10).default(5),
  metadata: z.record(z.string(), z.unknown()).default({}),
});

const setDesktopAttentionOverrideSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  subjectKind: z.string().min(1),
  subjectId: z.string().min(1),
  dismissed: z.boolean().default(true),
  hiddenUntilMs: z.coerce.number().int().positive().nullable().optional(),
  reason: z.string().min(1).optional(),
});

const evidenceRefSchema = strictObject({
  kind: z.enum([
    "conversation",
    "memory_item",
    "workstream_event",
    "artifact",
    "chat_message",
    "local_screen",
    "external",
  ]),
  id: z.string().min(1),
  version: z.string().min(1).optional(),
  scope: z.enum(["canonical", "device_local"]),
  device_id: z.string().min(1).optional(),
  excerpt_hash: z.string().min(1).optional(),
});

const prepareWorkstreamContinuitySchema = strictObject({
  ownerId: z.string().min(1).optional(),
  workstreamId: z.string().min(1),
  taskIds: z.array(z.string().min(1)).max(100).default([]),
  checkpoint: strictObject({
    checkpointId: z.string().min(1),
    runtimeId: z.string().min(1),
    lastEventSequence: z.coerce.number().int().nonnegative(),
    contextSummary: z.string().max(4_000),
    evidenceRefs: z.array(evidenceRefSchema).max(50).default([]),
    updatedAtMs: z.coerce.number().int().positive(),
  })
    .nullable()
    .optional(),
});

const persistWorkstreamContinuitySchema = strictObject({
  ownerId: z.string().min(1).optional(),
  workstreamId: z.string().min(1),
  context: z.record(z.string(), z.unknown()),
  artifacts: z
    .array(
      strictObject({
        logicalKey: z.string().min(1).max(256),
        evidenceRefs: z.array(evidenceRefSchema).min(1).max(20),
        kind: z.string().min(1),
        role: z.enum(["input", "result", "checkpoint", "tool_output", "log", "other"]),
        uri: z.string().min(1),
        displayName: z.string().nullable().optional(),
        mimeType: z.string().nullable().optional(),
        contentHash: z.string().nullable().optional(),
        sizeBytes: z.coerce.number().int().nonnegative().nullable().optional(),
        runId: z.string().nullable().optional(),
        attemptId: z.string().nullable().optional(),
        sourceArtifactId: z.string().min(1),
      }),
    )
    .max(50),
  ttlMs: z.coerce
    .number()
    .int()
    .positive()
    .max(7 * 24 * 60 * 60 * 1_000)
    .default(7 * 24 * 60 * 60 * 1_000),
});

const persistPreparedWorkstreamArtifactSchema = strictObject({
  ownerId: z.string().min(1).optional(),
  workstreamId: z.string().min(1),
  logicalKey: z.string().min(1).max(256),
  evidenceRefs: z.array(evidenceRefSchema).min(1).max(20),
  kind: z.string().min(1),
  uri: z.string().min(1),
  contentHash: z.string().min(16),
  sourceArtifactId: z.string().min(1),
  grantId: z.string().min(1),
});

const resolveWorkstreamContinuityDeliverySchema = strictObject({
  ownerId: z.string().min(1).optional(),
  deliveryId: z.string().min(1),
  status: z.enum(["delivered", "failed", "retrying"]),
  receipt: z.record(z.string(), z.unknown()).optional(),
  error: z.record(z.string(), z.unknown()).optional(),
});

const projectWorkstreamContinuitySchema = strictObject({
  ownerId: z.string().min(1).optional(),
  workstreamId: z.string().min(1),
});

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
  set_desktop_attention_override: setDesktopAttentionOverrideSchema,
  prepare_workstream_continuity: prepareWorkstreamContinuitySchema,
  persist_workstream_continuity: persistWorkstreamContinuitySchema,
  persist_prepared_workstream_artifact: persistPreparedWorkstreamArtifactSchema,
  resolve_workstream_continuity_delivery: resolveWorkstreamContinuityDeliverySchema,
  project_workstream_continuity: projectWorkstreamContinuitySchema,
} as const;

export type AgentControlToolName = keyof typeof agentControlToolSchemas;

export const INTERNAL_AGENT_CONTROL_TOOL_NAMES = [
  "prepare_workstream_continuity",
  "persist_workstream_continuity",
  "persist_prepared_workstream_artifact",
  "resolve_workstream_continuity_delivery",
  "project_workstream_continuity",
] as const satisfies readonly AgentControlToolName[];

export const AGENT_CONTROL_TOOL_NAMES = agentControlCapabilityManifest.map(
  (tool) => tool.name,
) as AgentControlToolName[];

/** App-callable tools advertised to Swift; internal continuity RPCs stay out of model manifests. */
export const SWIFT_ADVERTISED_AGENT_CONTROL_TOOL_NAMES = [
  ...AGENT_CONTROL_TOOL_NAMES.filter((name) => name !== "spawn_background_agent"),
  ...INTERNAL_AGENT_CONTROL_TOOL_NAMES,
] as AgentControlToolName[];

const CONTROL_TOOL_NAME_SET = new Set<string>(Object.keys(agentControlToolSchemas));

export interface AgentControlToolDefinition {
  name: AgentControlToolName;
  description: string;
  inputSchema: Record<string, unknown>;
}

export const agentControlToolDefinitions: AgentControlToolDefinition[] = agentControlCapabilityManifest.map((tool) => ({
  name: tool.name,
  description: tool.description,
  inputSchema: agentControlInputSchema(tool),
}));

export interface AgentControlToolContext {
  kernel: AgentRuntimeKernel;
  /**
   * The adapter selected by the owning desktop surface.  New background work
   * must inherit this route rather than silently selecting a local provider.
   */
  defaultAdapterId?: string;
  /** Kernel-owned provider and role policy for the active control caller. */
  providerBoundary?: ProviderBoundary;
  executionRole?: AgentExecutionRole;
  /** Persisted caller session used for kernel-level spawn authority checks. */
  callerSessionId?: string;
  /** Kernel-synthesized authority; never copied from adapter/model metadata. */
  authorizedProducerJournal?: AgentSpawnProducerJournalDescriptor;
  authorizedCallerRunId?: string;
  trustedUserControl?: boolean;
  getOwnerId?: () => string;
  /** Broker-owned authority checked immediately around every physical effect. */
  executionLease?: {
    readonly signal: AbortSignal;
    assertCurrentAuthority(): void | Promise<void>;
    /** Direct desktop control retains admitted children through owner transition. */
    retainRun?(runId: string): void;
  };
  recoverRunInput?: (adapterId: string) => Pick<ExecuteAgentRunInput, "maxAttempts" | "recoverAfterError">;
  buildMcpServers?: (
    mode: "ask" | "act",
    cwd: string | undefined,
    sessionKey: string | undefined,
    context: McpServerBuildContext,
  ) => Record<string, unknown>[];
}

interface PartialAgentSpawnCancellation {
  runId: string;
  accepted?: boolean;
  dispatchAttempted?: boolean;
  adapterAcknowledged?: boolean;
  error?: string;
}

class PartialAgentSpawnError extends Error {
  readonly code: string;
  readonly details: {
    admittedRunIds: string[];
    cancellations: PartialAgentSpawnCancellation[];
    cause: string;
  };

  constructor(input: {
    cause: unknown;
    cancellations: PartialAgentSpawnCancellation[];
  }) {
    const causeMessage = input.cause instanceof Error ? input.cause.message : String(input.cause);
    const cleanupFailed = input.cancellations.some((cancellation) => cancellation.error !== undefined);
    const causeCode = input.cause && typeof input.cause === "object" && "code" in input.cause
      ? String((input.cause as { code: unknown }).code)
      : "";
    super(cleanupFailed
      ? `Agent spawn failed after admitting children, and compensation failed for at least one child: ${causeMessage}`
      : `Agent spawn failed after admitting children; every admitted child was cancelled: ${causeMessage}`);
    this.name = "PartialAgentSpawnError";
    this.code = /^[a-z0-9_]{1,64}$/.test(causeCode)
      ? causeCode
      : cleanupFailed ? "partial_spawn_cleanup_failed" : "partial_spawn_compensated";
    this.details = {
      admittedRunIds: input.cancellations.map((cancellation) => cancellation.runId),
      cancellations: input.cancellations,
      cause: causeMessage,
    };
  }
}

function controlRunRecovery(
  context: AgentControlToolContext,
  adapterId: string,
): Pick<ExecuteAgentRunInput, "maxAttempts" | "recoverAfterError"> {
  return context.recoverRunInput?.(adapterId) ?? {};
}

function defaultControlAdapterId(context: AgentControlToolContext): string {
  return context.defaultAdapterId ?? "acp";
}

function controlSpawnProfile(
  context: AgentControlToolContext,
  ownerId: string,
): { adapterId: string; modelProfile: string | null; workingDirectory: string | undefined } {
  if (context.callerSessionId) {
    const profile = context.kernel.sessionExecutionProfile(context.callerSessionId, ownerId);
    return {
      adapterId: profile.adapterId,
      modelProfile: profile.modelProfile,
      workingDirectory: profile.workingDirectory || undefined,
    };
  }
  if (context.trustedUserControl) {
    const preference = context.kernel.defaultExecutionProfilePreference(ownerId);
    if (preference) {
      return {
        adapterId: preference.adapterId,
        modelProfile: preference.modelProfile,
        workingDirectory: preference.workingDirectory,
      };
    }
  }
  return {
    adapterId: defaultControlAdapterId(context),
    modelProfile: null,
    workingDirectory: undefined,
  };
}

function assertAdapterAllowedForControlRun(context: AgentControlToolContext, adapterId: string): void {
  if (!context.defaultAdapterId && !context.providerBoundary) {
    return;
  }
  const owningAdapterId = defaultControlAdapterId(context);
  resolveAdapterWithinBoundary({
    providerBoundary: context.providerBoundary ?? providerBoundaryForAdapter(owningAdapterId),
    defaultAdapterId: owningAdapterId,
    requestedAdapterId: adapterId,
  });
}

/**
 * A signed desktop action, or the explicit `provider` selector on the canonical
 * top-level spawn_agent tool, may start a new local-provider session. The
 * active bridge can still be pi-mono because it is only carrying the control
 * RPC; it is not the owner of the new session's credentials.
 *
 * An adapterId alone does not get this exception, and neither does any
 * parent-linked delegation. Those must stay inside the caller's persisted
 * provider boundary.
 */
function assertAdapterAllowedForTopLevelLocalProviderSpawn(
  context: AgentControlToolContext,
  adapterId: string,
  directedProvider?: "hermes" | "openclaw",
): void {
  const hasDirectedLocalProvider = directedProvider === adapterId;
  if (!context.trustedUserControl && !hasDirectedLocalProvider) {
    assertAdapterAllowedForControlRun(context, adapterId);
    return;
  }
  if (!isProductionAdapterId(adapterId)) {
    throw new Error(`Unknown production adapter: ${adapterId}`);
  }
  resolveAdapterWithinBoundary({
    providerBoundary: providerBoundaryForAdapter(adapterId),
    defaultAdapterId: adapterId,
    requestedAdapterId: adapterId,
  });
}

/**
 * Signed direct control resumes the target session's persisted boundary. This
 * keeps a user-selected Hermes/OpenClaw pill usable while the coordinator
 * bridge itself is using Omi cloud routing, and still prevents adapter changes
 * on either local or managed sessions.
 */
function assertAdapterAllowedForDirectSessionContinuation(
  context: AgentControlToolContext,
  adapterId: string,
  targetPolicy: Pick<AgentSession, "providerBoundary" | "defaultAdapterId">,
): void {
  if (!context.trustedUserControl) {
    assertAdapterAllowedForControlRun(context, adapterId);
    return;
  }
  resolveAdapterWithinBoundary({
    providerBoundary: targetPolicy.providerBoundary,
    defaultAdapterId: targetPolicy.defaultAdapterId,
    requestedAdapterId: adapterId,
  });
}

function assertAgentSpawningAllowed(context: AgentControlToolContext): void {
  if (context.executionRole === "leaf") {
    throw new Error("Background agents are leaf workers and cannot start additional agents.");
  }
}

function assertLeafControlToolsAllowed(context: AgentControlToolContext, name: string): void {
  if (!LEAF_AGENT_CONTROL_TOOLS.has(name)) return;
  if (!executionRoleAllowsTool(context.executionRole ?? "coordinator", name)) {
    throw new Error(
      name === "send_agent_message"
        ? "Leaf workers cannot continue agent sessions."
        : "Background agents are leaf workers and cannot start additional agents.",
    );
  }
}

function backgroundSpawnAuthority(context: AgentControlToolContext): {
  callerSessionId?: string;
  trustedUserSpawn?: boolean;
} {
  if (context.callerSessionId) {
    return { callerSessionId: context.callerSessionId };
  }
  if (context.trustedUserControl === true || context.executionRole !== "leaf") {
    return { trustedUserSpawn: true };
  }
  return {};
}

export const DEFAULT_LOCAL_OWNER_ID = "desktop-local-user";

export function withDefaultOwnerGuard(input: Record<string, unknown>, ownerGuard: string): Record<string, unknown> {
  if (Object.hasOwn(input, "ownerId")) {
    return input;
  }
  return { ...input, ownerId: ownerGuard };
}

export function withMergedOwnerGuard(
  input: Record<string, unknown>,
  ownerGuard: string | undefined,
  defaultOwnerGuard: string,
): Record<string, unknown> {
  if (!ownerGuard) {
    return withDefaultOwnerGuard(input, defaultOwnerGuard);
  }
  if (!Object.hasOwn(input, "ownerId")) {
    return { ...input, ownerId: ownerGuard };
  }
  const inputOwnerId = typeof input.ownerId === "string" ? input.ownerId.trim() : undefined;
  if (inputOwnerId !== ownerGuard) {
    throw new Error("Owner guards do not match");
  }
  return { ...input, ownerId: ownerGuard };
}

export function isAgentControlToolName(name: string): name is AgentControlToolName {
  return CONTROL_TOOL_NAME_SET.has(name);
}

async function executeAuthorizedControlEffect<T>(
  context: AgentControlToolContext,
  effect: () => T | Promise<T>,
): Promise<T> {
  await context.executionLease?.assertCurrentAuthority();
  if (context.executionLease?.signal.aborted) {
    throw context.executionLease.signal.reason instanceof Error
      ? context.executionLease.signal.reason
      : new Error("Run tool execution authority was revoked");
  }
  const result = await effect();
  await context.executionLease?.assertCurrentAuthority();
  return result;
}

export async function handleAgentControlToolCall(
  context: AgentControlToolContext,
  name: string,
  input: Record<string, unknown>,
): Promise<string> {
  if (!isAgentControlToolName(name)) {
    return JSON.stringify({
      ok: false,
      error: {
        code: "unknown_control_tool",
        message: `Unknown control tool: ${name}`,
      },
    });
  }
  if (name === "resolve_desktop_dispatch" && !context.trustedUserControl) {
    return JSON.stringify({
      ok: false,
      error: {
        code: "policy_denied",
        message: "resolve_desktop_dispatch requires trusted user control",
      },
    });
  }

  try {
    assertLeafControlToolsAllowed(context, name);
    switch (name) {
      case "list_agent_sessions": {
        const parsed = agentControlToolSchemas.list_agent_sessions.parse(input);
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const sessions = context.kernel.listSessions({
          ...parsed,
          ownerId,
        });
        const overrides = context.kernel.listDesktopAttentionOverrides(ownerId);
        return stringifyToolResult(serializeAgentSessionsList(sessions, overrides));
      }
      case "get_agent_run": {
        const parsed = agentControlToolSchemas.get_agent_run.parse(input);
        const details = context.kernel.getRun({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
        });
        return stringifyToolResult(serializeRunDetails(details));
      }
      case "build_desktop_awareness_snapshot": {
        const parsed = agentControlToolSchemas.build_desktop_awareness_snapshot.parse(input);
        const snapshot = context.kernel.buildDesktopAwarenessSnapshot({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
        });
        return stringifyToolResult({
          snapshot: serializeAwarenessSnapshot(snapshot),
        });
      }
      case "list_desktop_action_queue": {
        const parsed = agentControlToolSchemas.list_desktop_action_queue.parse(input);
        const actionQueue = context.kernel.listDesktopActionQueue({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
        });
        return stringifyToolResult({ actionQueue });
      }
      case "get_desktop_open_loops": {
        const parsed = agentControlToolSchemas.get_desktop_open_loops.parse(input);
        const openLoops = context.kernel.getDesktopOpenLoops({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
        });
        return stringifyToolResult({ openLoops });
      }
      case "build_desktop_context_packet": {
        const parsed = agentControlToolSchemas.build_desktop_context_packet.parse(input);
        const built = await executeAuthorizedControlEffect(context, () =>
          context.kernel.persistDesktopContextPacket({
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
            retentionClass: parsed.retentionClass,
          }));
        return stringifyToolResult({
          packet: {
            ...built.packet,
            packetJson: built.packet.packetJson,
            redactedPreviewJson: built.packet.redactedPreviewJson,
          },
          accessLogs: built.accessLogs,
        });
      }
      case "route_desktop_intent": {
        const parsed = agentControlToolSchemas.route_desktop_intent.parse(input);
        const route = context.kernel.routeDesktopIntent({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
          callerSessionId: context.callerSessionId,
          taskId: parsed.taskId ?? null,
        });
        return stringifyToolResult({ route });
      }
      case "evaluate_desktop_tool_policy": {
        const parsed = agentControlToolSchemas.evaluate_desktop_tool_policy.parse(input);
        const policy = evaluateDesktopToolPolicy({
          ...parsed,
          selectedBundles: parsed.selectedBundles as DesktopCoordinatorBundle[],
          requestedBundles: parsed.requestedBundles as DesktopCoordinatorBundle[] | undefined,
        });
        return stringifyToolResult({ policy });
      }
      case "create_desktop_dispatch": {
        const parsed = agentControlToolSchemas.create_desktop_dispatch.parse(input);
        const dispatch = await executeAuthorizedControlEffect(context, () => context.kernel.createDesktopDispatch({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
          payloadJson: JSON.stringify(parsed.payload),
        }));
        return stringifyToolResult({ dispatch });
      }
      case "resolve_desktop_dispatch": {
        const parsed = agentControlToolSchemas.resolve_desktop_dispatch.parse(input);
        const result = await executeAuthorizedControlEffect(context, () => context.kernel.resolveDesktopDispatch(parsed.dispatchId, {
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
          status: parsed.status,
          resolvedBy: parsed.resolvedBy ?? "user",
          resolutionJson: JSON.stringify(parsed.resolution),
          grant: parsed.grant,
        }));
        return stringifyToolResult({
          dispatch: result.dispatch,
          grant: result.grant,
          event: result.event ? serializeEvent(result.event) : null,
        });
      }
      case "cancel_agent_run": {
        const parsed = agentControlToolSchemas.cancel_agent_run.parse(input);
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const cancellation = await executeAuthorizedControlEffect(context, () =>
          context.kernel.cancelRun(parsed.runId, { ownerId }));
        const details = context.kernel.getRun({
          runId: parsed.runId,
          ownerId,
          includeEvents: true,
          eventLimit: 100,
        });
        return stringifyToolResult({
          cancellation,
          run: serializeRun(details.run),
          attempts: details.attempts.map(serializeAttempt),
        });
      }
      case "inspect_agent_artifacts": {
        const parsed = agentControlToolSchemas.inspect_agent_artifacts.parse(input);
        const artifacts = context.kernel.inspectArtifacts({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
        });
        return stringifyToolResult({
          artifacts: artifacts.map(serializeArtifact),
        });
      }
      case "update_agent_artifact_lifecycle": {
        const parsed = agentControlToolSchemas.update_agent_artifact_lifecycle.parse(input);
        const result = await executeAuthorizedControlEffect(context, () => context.kernel.updateArtifactLifecycle({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
        }));
        return stringifyToolResult({
          artifact: serializeArtifact(result.artifact),
          changed: result.changed,
          event: result.event ? serializeEvent(result.event) : null,
        });
      }
      case "send_agent_message": {
        const parsed = agentControlToolSchemas.send_agent_message.parse(input);
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const targetPolicy = context.kernel.executionPolicyForOwnedSession(parsed.sessionId, ownerId);
        const adapterId = parsed.adapterId ?? targetPolicy.defaultAdapterId;
        assertAdapterAllowedForDirectSessionContinuation(context, adapterId, targetPolicy);
        rejectSynchronousNestedRun(context, adapterId, parsed.sessionId);
        const requestId = parsed.requestId ?? `send-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        const routed = await executeAuthorizedControlEffect(context, () => context.kernel.applyDesktopIntentEffect(
          {
            ownerId,
            callerSessionId: context.callerSessionId,
            restrictiveCallerExecutionRole: context.executionRole,
            surfaceKind: parsed.originSurfaceKind,
            snapshotVersion: controlRouteSnapshotVersion(parsed.metadata),
            utterance: parsed.prompt,
            effect: "continue_run",
            syntaxFacts: {
              explicitSessionId: parsed.sessionId,
              explicitProvider: adapterId,
            },
          },
          () => context.kernel.sendAgentMessage({
            ...parsed,
            ...controlRunRecovery(context, adapterId),
            ownerId,
            requestId,
            metadata: { ...(parsed.metadata ?? {}) },
            authoritySignal: context.executionLease?.signal,
            mcpServers: buildControlRunMcpServers(context, {
              mode: parsed.mode,
              cwd: parsed.cwd,
              ownerId,
              requestId,
              clientId: parsed.clientId,
              adapterId,
              screenContext: true,
              executionRole: targetPolicy.executionRole,
            }),
          }),
        ));
        const result = routed.result;
        return stringifyToolResult({
          routeDecision: routed.decision,
          session: serializeSession(result.session),
          run: serializeRun(result.run),
          attempt: serializeAttempt(result.attempt),
          adapterSessionId: result.adapterSessionId,
          terminalStatus: result.terminalStatus,
          text: result.text,
          artifacts: result.artifacts.map(serializeArtifact),
        });
      }
      case "spawn_background_agent": {
        assertAgentSpawningAllowed(context);
        const parsed = agentControlToolSchemas.spawn_background_agent.parse(input);
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const requestId = parsed.requestId ?? `background-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        const spawnProfile = controlSpawnProfile(context, ownerId);
        const adapterId = parsed.adapterId ?? parsed.defaultAdapterId ?? spawnProfile.adapterId;
        const cwd = parsed.cwd ?? spawnProfile.workingDirectory;
        const model = parsed.model ?? spawnProfile.modelProfile ?? undefined;
        assertAdapterAllowedForTopLevelLocalProviderSpawn(context, adapterId);
        const routed = await executeAuthorizedControlEffect(context, () => context.kernel.applyDesktopIntentEffect(
          {
            ownerId,
            callerSessionId: context.callerSessionId,
            restrictiveCallerExecutionRole: context.executionRole,
            surfaceKind: parsed.originSurfaceKind,
            snapshotVersion: controlRouteSnapshotVersion(parsed.metadata),
            utterance: parsed.prompt,
            effect: "spawn_agent",
            syntaxFacts: {
              explicitProvider: adapterId,
              requestedAgentCount: 1,
            },
          },
          () => context.kernel.spawnBackgroundAgent({
            ...parsed,
            ...controlRunRecovery(context, adapterId),
            ...backgroundSpawnAuthority(context),
            adapterId,
            defaultAdapterId: adapterId,
            cwd,
            model,
            ownerId,
            requestId,
            surfaceKind: parsed.surfaceKind ?? "floating_bar",
            metadata: { ...(parsed.metadata ?? {}) },
            authoritySignal: context.executionLease?.signal,
            mcpServers: buildControlRunMcpServers(context, {
              mode: parsed.mode,
              cwd,
              ownerId,
              requestId,
              clientId: parsed.clientId,
              adapterId,
              screenContext: true,
              executionRole: "leaf",
            }),
          }),
        ));
        const result = routed.result;
        context.executionLease?.retainRun?.(result.run.runId);
        return stringifyToolResult({
          routeDecision: routed.decision,
          session: serializeSession(result.session),
          run: serializeRun(result.run),
          attempt: result.attempt ? serializeAttempt(result.attempt) : null,
        });
      }
      case "spawn_agent": {
        assertAgentSpawningAllowed(context);
        const parsed = authorizedSpawnAgentSchema.parse(input);
        const callerMetadata = { ...(parsed.metadata ?? {}) };
        const proposedProducerJournal = callerMetadata.producerJournal;
        delete callerMetadata.producerJournal;
        let producerJournal = context.authorizedProducerJournal;
        if (!producerJournal && context.trustedUserControl && proposedProducerJournal !== undefined) {
          producerJournal = parseAgentSpawnProducerJournalDescriptor(proposedProducerJournal);
          if (producerJournal.producerTurnId) {
            throw new Error("producerTurnId is reserved for kernel-authorized spawn invocations");
          }
        }
        const parentRunId = context.authorizedCallerRunId ?? parsed.parentRunId;
        if (context.authorizedCallerRunId && parsed.parentRunId && parsed.parentRunId !== context.authorizedCallerRunId) {
          throw new Error("Agent spawn parent run does not match authorized caller run");
        }
        if (parentRunId) {
          assertCanonicalRunId(parentRunId, "parentRunId");
        }
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const spawnProfile = controlSpawnProfile(context, ownerId);
        const requestId = parsed.requestId ?? `spawn-agent-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        if (parsed.provider && parsed.adapterId && parsed.provider !== parsed.adapterId) {
          throw new Error("provider and adapterId must match when both are supplied");
        }
        const adapterId =
          parsed.adapterId ??
          (parsed.provider === "openclaw" ? "openclaw" : parsed.provider === "hermes" ? "hermes" : undefined) ??
          (parentRunId
            ? context.kernel.defaultAdapterIdForRun(parentRunId)
            : spawnProfile.adapterId);
        /**
         * Realtime control always stamps its own run as `parentRunId` so the
         * producer journal is bound to the exact authorized turn.  That
         * provenance must not turn an explicit user-selected local provider
         * into a child of the managed pi-mono session: delegateAgent correctly
         * pins children to their parent's credential boundary.
         *
         * The exception is deliberately narrow.  It requires both the
         * kernel-issued realtime caller/run and its producer-journal
         * descriptor, an explicit provider selector, and no producerTurnId
         * whose validation requires an actual child parent_run_id.  Normal
         * parent-linked delegation stays on the existing boundary-safe path.
         */
        const isAuthorizedIndependentLocalProviderSpawn = Boolean(
          parentRunId
          && context.authorizedCallerRunId === parentRunId
          && context.authorizedProducerJournal
          && parsed.provider
          && parsed.provider === adapterId
          && !producerJournal?.producerTurnId,
        );
        const inheritsParentExecutionProfile = Boolean(parentRunId) && !isAuthorizedIndependentLocalProviderSpawn;
        const cwd = parsed.cwd ?? (inheritsParentExecutionProfile ? undefined : spawnProfile.workingDirectory);
        // An explicitly selected local provider is a new credential/model
        // boundary.  Its adapter owns model selection, so it must not inherit
        // the managed Omi model profile from the realtime coordinator (for
        // example `omi-sonnet`, which Hermes/OpenClaw cannot use with a Codex
        // ChatGPT account).  An explicitly supplied model remains intentional
        // user/provider input; ordinary parent-linked children still inherit.
        const model = parsed.model ?? (
          inheritsParentExecutionProfile || parsed.provider
            ? undefined
            : spawnProfile.modelProfile ?? undefined
        );
        if (inheritsParentExecutionProfile) {
          assertAdapterAllowedForControlRun(context, adapterId);
        } else {
          assertAdapterAllowedForTopLevelLocalProviderSpawn(context, adapterId, parsed.provider);
        }
        const childSurfaceKind = parsed.visible ? "floating_bar" : "delegated_agent";
        const childExternalRefKind = parsed.visible ? "pill" : undefined;
        const producerContextSnapshot = (!parentRunId || isAuthorizedIndependentLocalProviderSpawn) && producerJournal
          ? context.kernel.contextSnapshotForExactSurface(ownerId, producerJournal.surface)
          : undefined;
        const routed = await context.kernel.applyDesktopIntentEffect(
          {
            ownerId,
            callerSessionId: context.callerSessionId,
            restrictiveCallerExecutionRole: context.executionRole,
            surfaceKind: parsed.originSurfaceKind,
            snapshotVersion: controlRouteSnapshotVersion(parsed.metadata),
            utterance: parsed.objective,
            effect: "spawn_agent",
            syntaxFacts: {
              parentRunId,
              explicitProvider: adapterId,
              requestedAgentCount: parsed.requestedAgentCount,
            },
          },
          async () => {
            const siblings: Array<
              | { kind: "delegated"; result: Awaited<ReturnType<AgentRuntimeKernel["delegateAgent"]>> }
              | { kind: "background"; result: Awaited<ReturnType<AgentRuntimeKernel["spawnBackgroundAgent"]>> }
            > = [];
            try {
              for (let index = 0; index < parsed.requestedAgentCount; index += 1) {
                const ordinal = index + 1;
                const siblingRequestId = parsed.requestedAgentCount === 1 ? requestId : `${requestId}:${ordinal}`;
                const siblingExternalRefId = parsed.visible
                  ? parsed.requestedAgentCount === 1
                    ? (parsed.externalRefId ?? randomUUID())
                    : randomUUID()
                  : parsed.externalRefId;
                const titleSuffix = parsed.requestedAgentCount === 1 ? "" : ` (${ordinal}/${parsed.requestedAgentCount})`;
                const childTitle = `${parsed.title ?? `${parentRunId ? "Delegated" : "Background"}: ${parsed.objective.slice(0, 80)}`}${titleSuffix}`;
                const siblingProducerJournal = producerJournal && siblingExternalRefId
                  ? {
                      ...producerJournal,
                      continuityKey: parsed.requestedAgentCount === 1
                        ? producerJournal.continuityKey
                        : `${producerJournal.continuityKey}:${ordinal}`,
                      pillId: siblingExternalRefId,
                      objective: parsed.objective,
                      title: childTitle,
                    }
                  : undefined;
                const siblingMetadata = {
                  ...callerMetadata,
                  visible: parsed.visible,
                  siblingOrdinal: ordinal,
                  ...(parsed.brief ? { brief: parsed.brief } : {}),
                  ...(parsed.requestedAgentCount > 1 && parsed.externalRefId
                    ? { siblingGroupExternalRefId: parsed.externalRefId }
                    : {}),
                  ...(parsed.visible && siblingExternalRefId ? { pillId: siblingExternalRefId } : {}),
                  ...(siblingProducerJournal ? { producerJournal: siblingProducerJournal } : {}),
                };
                const mcpServers = buildControlRunMcpServers(context, {
                  mode: "act",
                  cwd,
                  ownerId,
                  requestId: siblingRequestId,
                  clientId: parsed.clientId,
                  adapterId: adapterId ?? defaultControlAdapterId(context),
                  surfaceKind: childSurfaceKind,
                  externalRefKind: childExternalRefKind,
                  externalRefId: siblingExternalRefId,
                  screenContext: true,
                  executionRole: "leaf",
                });
                if (inheritsParentExecutionProfile) {
                  if (!parentRunId) {
                    throw new Error("Parent-linked agent spawn is missing its parent run");
                  }
                  const result = await executeAuthorizedControlEffect(context, () => context.kernel.delegateAgent({
                    ...controlRunRecovery(context, adapterId ?? defaultControlAdapterId(context)),
                    mode: "spawn",
                    parentRunId,
                    objective: parsed.objective,
                    ownerId,
                    requestId: siblingRequestId,
                    adapterId,
                    defaultAdapterId: adapterId,
                    childSurfaceKind,
                    childExternalRefKind,
                    childExternalRefId: siblingExternalRefId,
                    childTitle,
                    cwd,
                    model,
                    runMode: "act",
                    clientId: parsed.clientId,
                    metadata: siblingMetadata,
                    authoritySignal: context.executionLease?.signal,
                    mcpServers,
                  }));
                  siblings.push({
                    kind: "delegated",
                    result,
                  });
                  context.executionLease?.retainRun?.(result.childRun.runId);
                } else {
                  const result = await executeAuthorizedControlEffect(context, () => context.kernel.spawnBackgroundAgent({
                    ...controlRunRecovery(context, adapterId ?? defaultControlAdapterId(context)),
                    ...(isAuthorizedIndependentLocalProviderSpawn
                      ? { trustedUserSpawn: true }
                      : backgroundSpawnAuthority(context)),
                    ownerId,
                    clientId: parsed.clientId,
                    requestId: siblingRequestId,
                    prompt: parsed.objective,
                    title: childTitle,
                    surfaceKind: childSurfaceKind,
                    externalRefKind: childExternalRefKind,
                    externalRefId: siblingExternalRefId,
                    adapterId,
                    defaultAdapterId: adapterId,
                    cwd,
                    model,
                    mode: "act",
                    metadata: {
                      ...siblingMetadata,
                      provider: parsed.provider ?? null,
                    },
                    admittedContextSnapshot: producerContextSnapshot,
                    authoritySignal: context.executionLease?.signal,
                    mcpServers,
                  }));
                  siblings.push({
                    kind: "background",
                    result,
                  });
                  context.executionLease?.retainRun?.(result.run.runId);
                }
              }
            } catch (error) {
              if (siblings.length === 0) throw error;
              const cancellations: PartialAgentSpawnCancellation[] = [];
              for (const sibling of siblings) {
                const runId = sibling.kind === "delegated"
                  ? sibling.result.childRun.runId
                  : sibling.result.run.runId;
                try {
                  const cancellation = await context.kernel.cancelRun(runId, { ownerId });
                  cancellations.push({
                    runId,
                    accepted: cancellation.accepted,
                    dispatchAttempted: cancellation.dispatchAttempted,
                    adapterAcknowledged: cancellation.adapterAcknowledged,
                  });
                } catch (cancellationError) {
                  cancellations.push({
                    runId,
                    error: cancellationError instanceof Error
                      ? cancellationError.message
                      : String(cancellationError),
                  });
                }
              }
              throw new PartialAgentSpawnError({ cause: error, cancellations });
            }
            return siblings;
          },
        );
        const agents = routed.result.map((sibling) => sibling.kind === "delegated"
          ? {
              kind: sibling.kind,
              delegation: serializeDelegation(sibling.result.delegation),
              session: serializeSession(sibling.result.childSession),
              run: serializeRun(sibling.result.childRun),
              attempt: sibling.result.childAttempt ? serializeAttempt(sibling.result.childAttempt) : null,
            }
          : {
              kind: sibling.kind,
              delegation: null,
              session: serializeSession(sibling.result.session),
              run: serializeRun(sibling.result.run),
              attempt: sibling.result.attempt ? serializeAttempt(sibling.result.attempt) : null,
            });
        const first = agents[0]!;
        return stringifyToolResult({
          routeDecision: routed.decision,
          requestedAgentCount: parsed.requestedAgentCount,
          agents,
          delegation: first.delegation,
          session: first.session,
          run: first.run,
          attempt: first.attempt,
        });
      }
      case "run_agent_and_wait": {
        assertAgentSpawningAllowed(context);
        const parsed = agentControlToolSchemas.run_agent_and_wait.parse(input);
        assertCanonicalRunId(parsed.parentRunId, "parentRunId");
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const requestId = parsed.requestId ?? `run-and-wait-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        const adapterId = parsed.adapterId ?? context.kernel.defaultAdapterIdForRun(parsed.parentRunId);
        assertAdapterAllowedForControlRun(context, adapterId);
        const routed = await executeAuthorizedControlEffect(context, () => context.kernel.applyDesktopIntentEffect(
          {
            ownerId,
            callerSessionId: context.callerSessionId,
            restrictiveCallerExecutionRole: context.executionRole,
            surfaceKind: parsed.originSurfaceKind,
            snapshotVersion: controlRouteSnapshotVersion(parsed.metadata),
            utterance: parsed.objective,
            effect: "spawn_agent",
            syntaxFacts: {
              parentRunId: parsed.parentRunId,
              explicitProvider: adapterId,
              requestedAgentCount: 1,
            },
          },
          () => context.kernel.delegateAgent({
            ...controlRunRecovery(context, adapterId),
            mode: "call",
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
            metadata: { ...(parsed.metadata ?? {}) },
            authoritySignal: context.executionLease?.signal,
            mcpServers: buildControlRunMcpServers(context, {
              mode: parsed.runMode,
              cwd: parsed.cwd,
              ownerId,
              requestId,
              clientId: parsed.clientId,
              adapterId,
              screenContext: true,
              executionRole: "leaf",
            }),
          }),
        ));
        const result = routed.result;
        return stringifyToolResult({
          routeDecision: routed.decision,
          delegation: serializeDelegation(result.delegation),
          session: serializeSession(result.childSession),
          run: serializeRun(result.childRun),
          attempt: result.childAttempt ? serializeAttempt(result.childAttempt) : null,
          adapterSessionId: result.adapterSessionId ?? null,
          terminalStatus: result.terminalStatus ?? null,
          result: result.result
            ? {
                ...result.result,
                artifacts: result.result.artifacts.map(serializeArtifact),
              }
            : null,
        });
      }
      case "set_desktop_attention_override": {
        const parsed = agentControlToolSchemas.set_desktop_attention_override.parse(input);
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const override = await executeAuthorizedControlEffect(context, () => context.kernel.setDesktopAttentionOverride({
          ownerId,
          subjectKind: parsed.subjectKind,
          subjectId: parsed.subjectId,
          dismissedAtMs: parsed.dismissed ? Date.now() : null,
          hiddenUntilMs: parsed.hiddenUntilMs ?? null,
          reason: parsed.reason ?? null,
        }));
        return stringifyToolResult({ override });
      }
      case "prepare_workstream_continuity": {
        const parsed = agentControlToolSchemas.prepare_workstream_continuity.parse(input);
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const migration = await executeAuthorizedControlEffect(context, () =>
          context.kernel.migrateTaskSessionsToWorkstreams({
            ownerId,
            mappings: parsed.taskIds.map((taskId) => ({
              taskId,
              workstreamId: parsed.workstreamId,
            })),
          }));
        let importedSession = null;
        if (parsed.checkpoint) {
          const now = Date.now();
          const createdAtMs = now;
          const checkpoint: WorkstreamContinuationCheckpoint = {
            checkpointId: parsed.checkpoint.checkpointId,
            ownerId,
            workstreamId: parsed.workstreamId,
            sourceRuntimeId: parsed.checkpoint.runtimeId,
            canonicalSummary: parsed.checkpoint.contextSummary,
            redactedCanonicalSummary: parsed.checkpoint.contextSummary,
            summarySensitivityTier: "private",
            currentTask: null,
            selectedEvents: [],
            artifactHeads: [],
            provenance: {
              snapshotVersion: `backend-checkpoint:${parsed.checkpoint.lastEventSequence}`,
              fetchedAtMs: now,
              source: "canonical_backend",
            },
            evidenceRefs: parsed.checkpoint.evidenceRefs as EvidenceRef[],
            lastEventSequence: parsed.checkpoint.lastEventSequence,
            createdAtMs,
            expiresAtMs: now + 7 * 24 * 60 * 60 * 1_000,
          };
          importedSession = await executeAuthorizedControlEffect(context, () =>
            context.kernel.importWorkstreamContinuationCheckpoint(checkpoint));
        }
        const session = await executeAuthorizedControlEffect(context, () => context.kernel.resolveWorkstreamSession({
          ownerId,
          workstreamId: parsed.workstreamId,
        }));
        const summary = context.kernel
          .listSessions({ ownerId, surfaceKind: "workstream", limit: 200 })
          .find((candidate) => candidate.session.sessionId === session.agentSessionId);
        const run = summary?.activeRun ?? summary?.latestRun ?? null;
        return stringifyToolResult({
          migration,
          importedSession,
          session,
          run: run
            ? {
                runId: run.runId,
                status: run.status,
                statusText: run.finalText,
                errorMessage: run.errorMessage,
                updatedAtMs: run.updatedAtMs,
                completedAtMs: run.completedAtMs,
              }
            : null,
          deliveries: context.kernel
            .listArtifactDeliveries({
              ownerId,
              targetRef: parsed.workstreamId,
              statuses: ["pending", "failed", "retrying"],
            })
            .map(serializeContinuityDelivery),
        });
      }
      case "persist_workstream_continuity": {
        const parsed = agentControlToolSchemas.persist_workstream_continuity.parse(input);
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const contextPacket = await executeAuthorizedControlEffect(context, () =>
          context.kernel.persistWorkstreamContextPacket({
            ownerId,
            workstreamId: parsed.workstreamId,
            objective: "Continue canonical workstream",
            context: parsed.context as unknown as WorkstreamProductContext,
          }));
        const artifactVersions: Array<ReturnType<AgentRuntimeKernel["persistWorkstreamArtifactVersion"]>> = [];
        for (const artifact of parsed.artifacts) {
          artifactVersions.push(await executeAuthorizedControlEffect(context, () =>
            context.kernel.persistWorkstreamArtifactVersion({
              ownerId,
              workstreamId: parsed.workstreamId,
              logicalKey: artifact.logicalKey,
              evidenceRefs: artifact.evidenceRefs as EvidenceRef[],
              sourceArtifactId: artifact.sourceArtifactId,
              artifact: {
                kind: artifact.kind,
                role: artifact.role,
                uri: artifact.uri,
                displayName: artifact.displayName ?? null,
                mimeType: artifact.mimeType ?? null,
                contentHash: artifact.contentHash ?? null,
                sizeBytes: artifact.sizeBytes ?? null,
                runId: artifact.runId ?? null,
                attemptId: artifact.attemptId ?? null,
                metadataJson: "{}",
              },
            })));
        }
        const checkpoint = await executeAuthorizedControlEffect(context, () =>
          context.kernel.exportWorkstreamContinuationCheckpoint({
            ownerId,
            workstreamId: parsed.workstreamId,
            // Device-local citations can support the local artifact record, but
            // must not cross the backend checkpoint boundary without a separate
            // export approval. The durable checkpoint remains useful with its
            // canonical evidence subset.
            context: canonicalCheckpointContext(parsed.context as unknown as WorkstreamProductContext),
            ttlMs: parsed.ttlMs,
          }));
        const artifactDeliveries: Array<ReturnType<AgentRuntimeKernel["queueArtifactDelivery"]>> = [];
        for (const [index, version] of artifactVersions.entries()) {
          const contentHash = version.artifact.contentHash ?? hashReadableFileArtifact(version.artifact.uri);
          artifactDeliveries.push(await executeAuthorizedControlEffect(context, () =>
            context.kernel.queueArtifactDelivery({
              deliveryId: `artifactDelivery:workstream:${parsed.workstreamId}:${parsed.artifacts[index]!.sourceArtifactId}`,
              artifactId: version.artifact.artifactId,
              ownerId,
              sourceSessionId: version.artifact.sessionId,
              sourceRunId: version.artifact.runId,
              sourceAttemptId: version.artifact.attemptId,
              intendedSurface: "canonical_workstream",
              targetKind: "task_chat",
              targetRef: parsed.workstreamId,
              contentHash,
              deliveryStatus: contentHash ? "pending" : "cancelled",
              errorJson: contentHash
                ? null
                : JSON.stringify({
                  code: "local_only_artifact",
                  message: "Artifact has no content hash and is not a readable local file",
                }),
              receiptJson: JSON.stringify({
                kind: "artifact_descriptor",
                sourceArtifactId: parsed.artifacts[index]!.sourceArtifactId,
                logicalKey: version.logicalKey,
                artifactKind: version.artifact.kind,
                uri: version.artifact.uri,
                contentHash,
                sourceRunId: version.artifact.runId,
                evidenceRefs: version.evidenceRefs,
              }),
            })));
        }
        const checkpointArtifactId = `artifact_${checkpoint.checkpointId}`;
        let checkpointArtifact;
        try {
          checkpointArtifact = context.kernel.inspectArtifacts({
            artifactId: checkpointArtifactId,
            ownerId,
            limit: 1,
          })[0];
        } catch {
          checkpointArtifact = undefined;
        }
        if (!checkpointArtifact) {
          const session = await executeAuthorizedControlEffect(context, () => context.kernel.resolveWorkstreamSession({
            ownerId,
            workstreamId: parsed.workstreamId,
          }));
          checkpointArtifact = await executeAuthorizedControlEffect(context, () => context.kernel.persistArtifact({
            artifactId: checkpointArtifactId,
            sessionId: session.agentSessionId,
            kind: "workstream_continuation_checkpoint",
            role: "checkpoint",
            uri: `omi-artifact://workstream-checkpoint/${checkpoint.checkpointId}`,
            displayName: "Workstream continuation checkpoint",
            metadata: { checkpoint },
          }));
        }
        const checkpointDelivery = await executeAuthorizedControlEffect(context, () =>
          context.kernel.queueArtifactDelivery({
            deliveryId: `artifactDelivery:workstream-checkpoint:${checkpoint.checkpointId}`,
            artifactId: checkpointArtifact.artifactId,
            ownerId,
            sourceSessionId: checkpointArtifact.sessionId,
            intendedSurface: "canonical_workstream",
            targetKind: "task_chat",
            targetRef: parsed.workstreamId,
            receiptJson: JSON.stringify({
              kind: "continuation_checkpoint",
              checkpoint,
            }),
          }));
        return stringifyToolResult({
          contextPacket: { packetId: contextPacket.packet.packetId },
          artifactVersions: artifactVersions.map((version, index) => ({
            sourceArtifactId: parsed.artifacts[index]?.sourceArtifactId,
            logicalKey: version.logicalKey,
            version: version.version,
            supersedesArtifactId: version.supersedesArtifactId,
            evidenceRefs: version.evidenceRefs,
            artifact: serializeArtifact(version.artifact),
          })),
          checkpoint,
          deliveries: [...artifactDeliveries, checkpointDelivery]
            .filter((delivery) => delivery.deliveryStatus !== "delivered" && delivery.deliveryStatus !== "cancelled")
            .map(serializeContinuityDelivery),
        });
      }
      case "persist_prepared_workstream_artifact": {
        const parsed = agentControlToolSchemas.persist_prepared_workstream_artifact.parse(input);
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const version = await executeAuthorizedControlEffect(context, () =>
          context.kernel.persistAuthorizedPreparedArtifact({
            ownerId,
            workstreamId: parsed.workstreamId,
            logicalKey: parsed.logicalKey,
            evidenceRefs: parsed.evidenceRefs as EvidenceRef[],
            sourceArtifactId: parsed.sourceArtifactId,
            grantId: parsed.grantId,
            artifact: {
              kind: parsed.kind,
              role: "result",
              uri: parsed.uri,
              contentHash: parsed.contentHash,
              metadataJson: JSON.stringify({ status: "awaiting_review" }),
            },
          }));
        const delivery = await executeAuthorizedControlEffect(context, () =>
          context.kernel.queueArtifactDelivery({
            deliveryId: `artifactDelivery:workstream:${parsed.workstreamId}:${parsed.sourceArtifactId}`,
            artifactId: version.artifact.artifactId,
            ownerId,
            sourceSessionId: version.artifact.sessionId,
            sourceRunId: version.artifact.runId,
            sourceAttemptId: version.artifact.attemptId,
            intendedSurface: "canonical_workstream",
            targetKind: "task_chat",
            targetRef: parsed.workstreamId,
            contentHash: parsed.contentHash,
            receiptJson: JSON.stringify({
              kind: "artifact_descriptor",
              sourceArtifactId: parsed.sourceArtifactId,
              logicalKey: version.logicalKey,
              artifactKind: version.artifact.kind,
              uri: version.artifact.uri,
              contentHash: parsed.contentHash,
              sourceRunId: version.artifact.runId,
              evidenceRefs: version.evidenceRefs,
            }),
          }));
        return stringifyToolResult({
          artifactVersion: {
            sourceArtifactId: parsed.sourceArtifactId,
            logicalKey: version.logicalKey,
            version: version.version,
            supersedesArtifactId: version.supersedesArtifactId,
            evidenceRefs: version.evidenceRefs,
            artifact: serializeArtifact(version.artifact),
          },
          deliveries:
            delivery.deliveryStatus === "delivered" || delivery.deliveryStatus === "cancelled"
              ? []
              : [serializeContinuityDelivery(delivery)],
        });
      }
      case "resolve_workstream_continuity_delivery": {
        const parsed = agentControlToolSchemas.resolve_workstream_continuity_delivery.parse(input);
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const current = context.kernel
          .listArtifactDeliveries({ ownerId, limit: 500 })
          .find((delivery) => delivery.deliveryId === parsed.deliveryId);
        if (!current) throw new Error(`Unknown continuity delivery ${parsed.deliveryId}`);
        const delivery = await executeAuthorizedControlEffect(context, () =>
          context.kernel.updateArtifactDelivery(parsed.deliveryId, {
            ownerId,
            deliveryStatus: parsed.status,
            attemptCount: current.attemptCount + 1,
            receiptJson: parsed.receipt ? JSON.stringify(parsed.receipt) : current.receiptJson,
            errorJson: parsed.error ? JSON.stringify(parsed.error) : current.errorJson,
            deliveredAtMs: parsed.status === "delivered" ? Date.now() : null,
          }));
        return stringifyToolResult({
          delivery: serializeContinuityDelivery(delivery),
        });
      }
      case "project_workstream_continuity": {
        const parsed = agentControlToolSchemas.project_workstream_continuity.parse(input);
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const projection = context.kernel.projectWorkstreamContinuity({
          ownerId,
          workstreamId: parsed.workstreamId,
        });
        return stringifyToolResult({
          projection: {
            ...projection,
            artifactVersions: projection.artifactVersions.map((version) => ({
              ...version,
              artifact: serializeArtifact(version.artifact),
            })),
          },
        });
      }
    }
  } catch (error) {
    const rawCode = error && typeof error === "object" && "code" in error
      ? String((error as { code: unknown }).code)
      : "";
    const details = error instanceof PartialAgentSpawnError ? error.details : undefined;
    const isAuthorizedExternalSpawnAdmission = name === "spawn_agent"
      && context.authorizedCallerRunId !== undefined
      && context.authorizedProducerJournal !== undefined;
    const errorCode = error instanceof z.ZodError
      ? "invalid_tool_input"
      : /^[a-z0-9_]{1,64}$/.test(rawCode) ? rawCode : "control_tool_failed";
    return JSON.stringify({
      ok: false,
      error: {
        // Realtime callers consume this response through a model tool result,
        // so an admission failure needs a stable recovery signal rather than
        // an adapter/policy exception that may contain implementation detail.
        code: isAuthorizedExternalSpawnAdmission && errorCode === "control_tool_failed"
          ? "external_spawn_admission_failed"
          : errorCode,
        message: isAuthorizedExternalSpawnAdmission && errorCode === "control_tool_failed"
          ? "The requested agent could not be started. Try again."
          : error instanceof Error ? error.message : String(error),
        ...(isAuthorizedExternalSpawnAdmission ? { retryable: true } : {}),
        ...(details ? { details } : {}),
      },
    });
  }
}

function buildControlRunMcpServers(
  context: AgentControlToolContext,
  input: {
    mode: "ask" | "act";
    cwd?: string;
    ownerId: string;
    requestId: string;
    clientId: string;
    adapterId: string;
    surfaceKind?: string;
    externalRefKind?: string;
    externalRefId?: string;
    screenContext?: boolean;
    executionRole?: AgentExecutionRole;
  },
): Record<string, unknown>[] | undefined {
  if (!context.buildMcpServers) {
    return undefined;
  }
  const servers = context.buildMcpServers(input.mode, input.cwd, undefined, {
    ownerId: input.ownerId,
    requestId: input.requestId,
    clientId: input.clientId,
    adapterId: input.adapterId,
    protocolVersion: 2,
    surfaceKind: input.surfaceKind,
    externalRefKind: input.externalRefKind,
    externalRefId: input.externalRefId,
    includeSwiftBackedTools: true,
    screenContext: input.screenContext === true,
    executionRole: input.executionRole,
  });
  return servers;
}

function assertCanonicalRunId(value: string, fieldName: string): void {
  if (!value.startsWith("run_")) {
    throw new Error(
      `${fieldName} must be a canonical Omi run_id starting with "run_"; omit it for a top-level background agent`,
    );
  }
}

function controlRouteSnapshotVersion(metadata: Record<string, unknown> | undefined): string {
  const value = metadata?.contextSnapshotVersion ?? metadata?.snapshotVersion;
  return typeof value === "string" && value.trim() ? value.trim() : "snapshot:control-unversioned";
}

function controlToolOwnerId(context: AgentControlToolContext): string {
  const ownerId = context.getOwnerId?.().trim();
  return ownerId || "desktop-local-user";
}


function effectiveControlToolOwnerId(context: AgentControlToolContext, requestedOwnerId?: string): string {
  const activeOwnerId = controlToolOwnerId(context);
  const ownerGuard = requestedOwnerId?.trim();
  if (requestedOwnerId !== undefined && !ownerGuard) {
    throw new Error("Requested ownerId cannot be empty");
  }
  if (ownerGuard && ownerGuard !== activeOwnerId) {
    throw new Error("Requested ownerId does not match the active control owner");
  }
  return activeOwnerId;
}

function rejectSynchronousNestedRun(context: AgentControlToolContext, adapterId: string, sessionId?: string): void {
  if (!context.kernel.isAdapterRegistered(adapterId)) {
    return;
  }
  if (
    (sessionId && context.kernel.hasActiveExecutionForSessionAdapter(sessionId, adapterId)) ||
    !context.kernel.hasExecutionCapacityForAdapter(adapterId)
  ) {
    throw new Error(
      `Synchronous ${adapterId} control-tool runs are unavailable while that adapter is already executing; use spawn mode or retry after the current run finishes.`,
    );
  }
}

function stringifyToolResult(payload: Record<string, unknown>): string {
  return JSON.stringify({ ok: true, ...payload });
}

function serializeContinuityDelivery(delivery: {
  deliveryId: string;
  artifactId: string;
  deliveryStatus: string;
  attemptCount: number;
  receiptJson: string | null;
  errorJson: string | null;
}): Record<string, unknown> {
  return {
    deliveryId: delivery.deliveryId,
    artifactId: delivery.artifactId,
    status: delivery.deliveryStatus,
    attemptCount: delivery.attemptCount,
    payload: delivery.receiptJson ? JSON.parse(delivery.receiptJson) : {},
    error: delivery.errorJson ? JSON.parse(delivery.errorJson) : null,
  };
}

function canonicalCheckpointContext(context: WorkstreamProductContext): WorkstreamProductContext {
  const canonicalEvidence = (refs: EvidenceRef[] | undefined): EvidenceRef[] | undefined =>
    refs?.filter((ref) => ref.scope === "canonical");
  return {
    ...context,
    selectedEvents: context.selectedEvents?.map((event) => ({
      ...event,
      evidenceRefs: canonicalEvidence(event.evidenceRefs),
    })),
    artifactHeads: context.artifactHeads?.map((artifact) => ({
      ...artifact,
      evidenceRefs: canonicalEvidence(artifact.evidenceRefs),
    })),
  };
}

function hashReadableFileArtifact(uri: string): string | null {
  if (!uri.startsWith("file://")) return null;
  try {
    return `sha256:${createHash("sha256")
      .update(readFileSync(fileURLToPath(uri)))
      .digest("hex")}`;
  } catch {
    return null;
  }
}

function serializeAgentSessionsList(
  sessions: Parameters<typeof serializeSessionSummary>[0][],
  overrides: {
    subjectKind: string;
    subjectId: string;
    dismissedAtMs?: number | null;
    hiddenUntilMs?: number | null;
  }[],
): Record<string, unknown> {
  const maximumSerializedBytes = 40 * 1024;
  const dismissed = new Set(
    overrides
      .filter((override) => override.dismissedAtMs != null || (override.hiddenUntilMs ?? 0) > Date.now())
      .map((override) => `${override.subjectKind}:${override.subjectId}`),
  );
  // Keep the canonical list operation compact. A session's persisted run input
  // can include hundreds of kilobytes of surface context, and returning that
  // here used to make a routine realtime `list_agent_sessions` response exceed
  // provider WebSocket limits. Full run/session detail remains available from
  // `get_agent_run` and the internal awareness snapshot.
  const serializedSessions: Record<string, unknown>[] = [];
  const floatingAgentPills: Record<string, unknown>[] = [];
  const taskAgents: Record<string, unknown>[] = [];
  let truncated = false;

  for (const summary of sessions) {
    const serializedSession = serializeSessionListSummary(summary);
    const run = summary.activeRun ?? summary.latestRun;
    const runId = run?.runId ?? null;
    const sessionId = summary.session.sessionId;
    const surfaceKind = summary.session.surfaceKind;
    const floatingPill = (
      (surfaceKind === "floating_bar" || surfaceKind === "background_agent" || surfaceKind === "floating_pill")
      && !(runId && dismissed.has(`run:${runId}`))
      && !dismissed.has(`session:${sessionId}`)
    ) ? serializeFloatingPillSnapshot(summary) : null;
    const taskAgent = surfaceKind === "task_chat" ? serializeTaskAgentSnapshot(summary) : null;

    serializedSessions.push(serializedSession);
    if (floatingPill) floatingAgentPills.push(floatingPill);
    if (taskAgent) taskAgents.push(taskAgent);
    const candidate = {
      sessions: serializedSessions,
      task_agents: taskAgents,
      floating_agent_pills: floatingAgentPills,
      truncated: false,
      fetched_session_count: sessions.length,
    };
    if (Buffer.byteLength(JSON.stringify({ ok: true, ...candidate }), "utf8") > maximumSerializedBytes) {
      serializedSessions.pop();
      if (floatingPill) floatingAgentPills.pop();
      if (taskAgent) taskAgents.pop();
      truncated = true;
      break;
    }
  }

  return {
    sessions: serializedSessions,
    task_agents: taskAgents,
    floating_agent_pills: floatingAgentPills,
    truncated,
    returned_session_count: serializedSessions.length,
    fetched_session_count: sessions.length,
  };
}

const CONTROL_LIST_TEXT_LIMIT = 512;

function boundedControlListText(value: unknown, limit = CONTROL_LIST_TEXT_LIMIT): string | null {
  if (typeof value !== "string" || value.length === 0) return null;
  return value.length <= limit ? value : `${value.slice(0, limit)}\n[truncated]`;
}

function serializeSessionListSummary(summary: {
  session: AgentSession;
  latestRun?: AgentRun;
  activeRun?: AgentRun;
  adapterBindings: AdapterBinding[];
}): Record<string, unknown> {
  const session = summary.session;
  return {
    session: {
      sessionId: session.sessionId,
      ownerId: session.ownerId,
      title: boundedControlListText(session.title, 160),
      status: session.status,
      surfaceKind: session.surfaceKind,
      executionRole: session.executionRole,
      externalRefKind: session.externalRefKind,
      externalRefId: session.externalRefId,
      defaultAdapterId: session.defaultAdapterId,
      modelProfile: session.modelProfile,
      createdAtMs: session.createdAtMs,
      updatedAtMs: session.updatedAtMs,
      lastActivityAtMs: session.lastActivityAtMs,
    },
    latestRun: summary.latestRun ? serializeRunListSummary(summary.latestRun) : null,
    activeRun: summary.activeRun ? serializeRunListSummary(summary.activeRun) : null,
    adapterBindings: summary.adapterBindings.map((binding) => ({
      bindingId: binding.bindingId,
      sessionId: binding.sessionId,
      adapterId: binding.adapterId,
      adapterNativeSessionId: binding.adapterNativeSessionId,
      resumeFidelity: binding.resumeFidelity,
      status: binding.status,
      modelId: binding.modelId,
      updatedAtMs: binding.updatedAtMs,
    })),
  };
}

function serializeRunListSummary(run: AgentRun): Record<string, unknown> {
  const input = parseJsonObject(run.inputJson) as Record<string, unknown>;
  return appendErrorFields(
    {
      runId: run.runId,
      sessionId: run.sessionId,
      parentRunId: run.parentRunId,
      status: run.status,
      mode: run.mode,
      input: {
        prompt: boundedControlListText(input.prompt),
      },
      requestedModelId: run.requestedModelId,
      finalText: boundedControlListText(run.finalText),
      createdAtMs: run.createdAtMs,
      startedAtMs: run.startedAtMs,
      completedAtMs: run.completedAtMs,
      updatedAtMs: run.updatedAtMs,
    },
    run.errorCode,
    boundedControlListText(run.errorMessage),
  );
}

function serializeFloatingPillSnapshot(summary: {
  session: AgentSession;
  latestRun?: AgentRun;
  activeRun?: AgentRun;
}): Record<string, unknown> {
  const session = summary.session;
  const run = summary.activeRun ?? summary.latestRun;
  const input = (run ? parseJsonObject(run.inputJson) : {}) as Record<string, unknown>;
  const metadata = parseJsonObject(session.metadataJson) as Record<string, unknown>;
  const runId = run?.runId ?? null;
  const sessionId = session.sessionId || null;
  const errorMessage = run?.errorMessage || null;
  const errorCode = run?.errorCode || null;
  const pillId =
    session.externalRefId ||
    (typeof metadata.pillId === "string" ? metadata.pillId : null) ||
    runId ||
    sessionId;
  const adapterId = session.defaultAdapterId;
  const authoritativeProvider = adapterId === "openclaw" || adapterId === "hermes"
    ? adapterId
    : null;
  const legacyProvider = metadata.provider === "openclaw" || metadata.provider === "hermes"
    ? metadata.provider
    : null;
  return {
    id: pillId,
    runId,
    sessionId,
    title: boundedControlListText(session.title, 160) ?? "Background agent",
    status: run?.status ?? session.status,
    latestActivity: boundedControlListText(run?.finalText ?? errorMessage ?? input.prompt ?? session.title ?? "") ?? "",
    query: boundedControlListText(input.prompt) ?? "",
    createdAtMs: session.createdAtMs ?? null,
    completedAtMs: run?.completedAtMs ?? null,
    provider: authoritativeProvider ?? legacyProvider,
    errorCode: boundedControlListText(errorCode, 128),
    errorMessage: boundedControlListText(errorMessage),
  };
}

function serializeTaskAgentSnapshot(summary: {
  session: AgentSession;
  latestRun?: AgentRun;
  activeRun?: AgentRun;
}): Record<string, unknown> {
  const session = summary.session;
  const run = summary.activeRun ?? summary.latestRun;
  return {
    taskId: session.externalRefId ?? null,
    sessionId: session.sessionId ?? null,
    runId: run?.runId ?? null,
    title: boundedControlListText(session.title, 160),
    status: run?.status ?? session.status,
    statusText: boundedControlListText(run?.finalText),
    lastError: boundedControlListText(run?.errorMessage),
    updatedAtMs: run?.updatedAtMs ?? session.updatedAtMs ?? null,
  };
}

function serializeSessionSummary(summary: {
  session: AgentSession;
  latestRun?: AgentRun;
  activeRun?: AgentRun;
  adapterBindings: AdapterBinding[];
}): Record<string, unknown> {
  return {
    session: serializeSession(summary.session),
    latestRun: summary.latestRun ? serializeRun(summary.latestRun) : null,
    activeRun: summary.activeRun ? serializeRun(summary.activeRun) : null,
    adapterBindings: summary.adapterBindings.map(serializeBinding),
  };
}

function serializeRunDetails(details: {
  session: AgentSession;
  run: AgentRun;
  attempts: RunAttempt[];
  adapterBindings: AdapterBinding[];
  artifacts: AgentArtifact[];
  events: AgentEvent[];
  parentDelegations: AgentDelegation[];
  childDelegations: AgentDelegation[];
  toolInvocations: Array<{
    invocationId: string;
    runId: string;
    attemptId: string;
    toolName: string;
    status: string;
    errorCode: string | null;
    preparedAtMs: number;
    dispatchedAtMs: number | null;
    completedAtMs: number | null;
    updatedAtMs: number;
  }>;
}): Record<string, unknown> {
  return {
    session: serializeSession(details.session),
    run: serializeRun(details.run),
    attempts: details.attempts.map(serializeAttempt),
    adapterBindings: details.adapterBindings.map(serializeBinding),
    artifacts: details.artifacts.map(serializeArtifact),
    events: details.events.map(serializeEvent),
    parentDelegations: details.parentDelegations.map(serializeDelegation),
    childDelegations: details.childDelegations.map(serializeDelegation),
    toolInvocations: details.toolInvocations,
  };
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
    runtime: snapshot.runtime,
  };
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
    lastActivityAtMs: session.lastActivityAtMs,
  };
}

function appendErrorFields(
  payload: Record<string, unknown>,
  errorCode: string | null | undefined,
  errorMessage: string | null | undefined,
): Record<string, unknown> {
  if (errorCode != null && errorCode !== "") {
    payload.errorCode = errorCode;
  }
  if (errorMessage != null && errorMessage !== "") {
    payload.errorMessage = errorMessage;
  }
  return payload;
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
        costUsd: run.costUsd,
      },
      createdAtMs: run.createdAtMs,
      startedAtMs: run.startedAtMs,
      completedAtMs: run.completedAtMs,
      updatedAtMs: run.updatedAtMs,
    },
    run.errorCode,
    run.errorMessage,
  );
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
      updatedAtMs: attempt.updatedAtMs,
    },
    attempt.errorCode,
    attempt.errorMessage,
  );
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
    invalidatedAtMs: binding.invalidatedAtMs,
  };
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
    createdAtMs: event.createdAtMs,
  };
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
    completedAtMs: delegation.completedAtMs,
  };
}

function parseOptionalJsonObject(value: string | null): unknown {
  return value === null ? null : parseJsonObject(value);
}

function parseJsonObject(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return { raw: value };
  }
}
