import { z } from "zod";
import type { AgentArtifact, AgentDelegation, AgentEvent, AgentRun, AgentSession, AdapterBinding, RunAttempt } from "./types.js";
import { AgentRuntimeKernel } from "./kernel.js";
import { agentControlCapabilityManifest, agentControlInputSchema } from "./control-tool-manifest.js";
import type { McpServerBuildContext } from "./compatibility-facade.js";

const sessionStatusSchema = z.enum(["open", "archived", "closed"]);
const artifactRoleSchema = z.enum(["input", "result", "checkpoint", "tool_output", "log", "other"]);
const artifactLifecycleStateSchema = z.enum(["retained", "dismissed", "opened"]);
const runModeSchema = z.enum(["ask", "act"]);
const delegationModeSchema = z.enum(["call", "spawn", "continue"]);

const listAgentSessionsSchema = z.object({
  ownerId: z.string().min(1).optional(),
  status: sessionStatusSchema.optional(),
  surfaceKind: z.string().min(1).optional(),
  limit: z.coerce.number().int().positive().max(200).default(50),
  beforeUpdatedAtMs: z.coerce.number().int().positive().optional(),
});

const getAgentRunSchema = z.object({
  runId: z.string().min(1),
  ownerId: z.string().min(1).optional(),
  includeEvents: z.boolean().default(true),
  eventLimit: z.coerce.number().int().positive().max(500).default(100),
});

const cancelAgentRunSchema = z.object({
  runId: z.string().min(1),
  ownerId: z.string().min(1).optional(),
});

const inspectAgentArtifactsSchema = z
  .object({
    sessionId: z.string().min(1).optional(),
    runId: z.string().min(1).optional(),
    attemptId: z.string().min(1).optional(),
    ownerId: z.string().min(1).optional(),
    role: artifactRoleSchema.optional(),
    limit: z.coerce.number().int().positive().max(200).default(50),
  })
  .refine((value) => value.sessionId || value.runId || value.attemptId, {
    message: "Provide sessionId, runId, or attemptId",
  });

const updateAgentArtifactLifecycleSchema = z.object({
  artifactId: z.string().min(1),
  state: artifactLifecycleStateSchema,
  sessionId: z.string().min(1).optional(),
  runId: z.string().min(1).optional(),
  attemptId: z.string().min(1).optional(),
  ownerId: z.string().min(1).optional(),
  reason: z.string().min(1).max(500).optional(),
  metadata: z.record(z.string(), z.unknown()).default({}),
});

const sendAgentMessageSchema = z.object({
  sessionId: z.string().min(1),
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

const delegateAgentSchema = z
  .object({
    mode: delegationModeSchema,
    parentRunId: z.string().min(1),
    objective: z.string().min(1),
    context: z.string().max(4000).optional(),
    ownerId: z.string().min(1).optional(),
    childSessionId: z.string().min(1).optional(),
    childSurfaceKind: z.string().min(1).default("delegated_agent"),
    childExternalRefKind: z.string().min(1).optional(),
    childExternalRefId: z.string().min(1).optional(),
    childTitle: z.string().min(1).optional(),
    adapterId: z.string().min(1).optional(),
    defaultAdapterId: z.string().min(1).optional(),
    cwd: z.string().min(1).optional(),
    model: z.string().min(1).optional(),
    runMode: runModeSchema.default("ask"),
    requestId: z.string().min(1).optional(),
    clientId: z.string().min(1).default("omi-control-tools"),
    maxDepth: z.coerce.number().int().min(1).max(5).default(3),
    maxBudgetUsd: z.coerce.number().positive().max(10).default(5),
    metadata: z.record(z.string(), z.unknown()).default({}),
  })
  .superRefine((value, ctx) => {
    if (value.mode === "continue" && !value.childSessionId) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["childSessionId"],
        message: "childSessionId is required for continue mode",
      });
    }
  });

export const agentControlToolSchemas = {
  list_agent_sessions: listAgentSessionsSchema,
  get_agent_run: getAgentRunSchema,
  cancel_agent_run: cancelAgentRunSchema,
  inspect_agent_artifacts: inspectAgentArtifactsSchema,
  update_agent_artifact_lifecycle: updateAgentArtifactLifecycleSchema,
  send_agent_message: sendAgentMessageSchema,
  delegate_agent: delegateAgentSchema,
} as const;

export type AgentControlToolName = keyof typeof agentControlToolSchemas;

export const AGENT_CONTROL_TOOL_NAMES = Object.keys(agentControlToolSchemas) as AgentControlToolName[];

const CONTROL_TOOL_NAME_SET = new Set<string>(AGENT_CONTROL_TOOL_NAMES);

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
  getOwnerId?: () => string;
  buildMcpServers?: (
    mode: "ask" | "act",
    cwd: string | undefined,
    sessionKey: string | undefined,
    context: McpServerBuildContext
  ) => Record<string, unknown>[];
  getProtocolVersion?: () => McpServerBuildContext["protocolVersion"];
}

export interface ActiveControlToolOwnerInput {
  requestKey?: string;
  runId?: string;
  attemptId?: string;
  ownerIdForRequest?: (requestKey: string) => string | undefined;
  ownerIdForRun?: (runId: string) => string | undefined;
  ownerIdForAttempt?: (attemptId: string) => string | undefined;
  fallbackOwnerId?: string;
  allowFallbackOwner?: boolean;
}

export interface ControlRequestKeyInput {
  requestId?: string;
  clientId?: string;
}

export interface ControlRequestContextInput extends ControlRequestKeyInput {
  ownerGuard?: string;
  fallbackOwnerId?: string;
}

export interface ResolvedControlRequestContext {
  requestKey?: string;
  activeOwnerId: string;
  ownerGuard?: string;
}

export const DEFAULT_LEGACY_JSONL_CLIENT_ID = "legacy-jsonl-client";

export function controlRequestKey(input: ControlRequestKeyInput): string | undefined {
  return input.requestId && input.clientId ? JSON.stringify([input.clientId, input.requestId]) : undefined;
}

export function legacyControlRequestKey(input: ControlRequestKeyInput): string | undefined {
  return input.requestId ? JSON.stringify([input.clientId ?? DEFAULT_LEGACY_JSONL_CLIENT_ID, input.requestId]) : undefined;
}

export function resolveControlRequestContext(input: ControlRequestContextInput): ResolvedControlRequestContext {
  const ownerGuard = input.ownerGuard?.trim();
  if (input.ownerGuard !== undefined && !ownerGuard) {
    throw new Error("ownerId cannot be empty");
  }
  const fallbackOwnerId = input.fallbackOwnerId?.trim();
  const activeOwnerId = fallbackOwnerId || "desktop-local-user";
  if (ownerGuard && ownerGuard !== activeOwnerId) {
    throw new Error("ownerId does not match active control owner");
  }
  return {
    requestKey: controlRequestKey(input),
    activeOwnerId,
    ownerGuard,
  };
}

export function withDefaultOwnerGuard(input: Record<string, unknown>, ownerGuard: string): Record<string, unknown> {
  if (Object.hasOwn(input, "ownerId")) {
    return input;
  }
  return { ...input, ownerId: ownerGuard };
}

export function withMergedOwnerGuard(
  input: Record<string, unknown>,
  ownerGuard: string | undefined,
  defaultOwnerGuard: string
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

export async function handleAgentControlToolCall(
  context: AgentControlToolContext,
  name: string,
  input: Record<string, unknown>
): Promise<string> {
  if (!isAgentControlToolName(name)) {
    return JSON.stringify({ ok: false, error: { code: "unknown_control_tool", message: `Unknown control tool: ${name}` } });
  }

  try {
    switch (name) {
      case "list_agent_sessions": {
        const parsed = agentControlToolSchemas.list_agent_sessions.parse(input);
        const sessions = context.kernel.listSessions({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
        });
        return stringifyToolResult({ sessions: sessions.map(serializeSessionSummary) });
      }
      case "get_agent_run": {
        const parsed = agentControlToolSchemas.get_agent_run.parse(input);
        const details = context.kernel.getRun({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
        });
        return stringifyToolResult(serializeRunDetails(details));
      }
      case "cancel_agent_run": {
        const parsed = agentControlToolSchemas.cancel_agent_run.parse(input);
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const cancellation = await context.kernel.cancelRun(parsed.runId, { ownerId });
        const details = context.kernel.getRun({ runId: parsed.runId, ownerId, includeEvents: true, eventLimit: 100 });
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
        return stringifyToolResult({ artifacts: artifacts.map(serializeArtifact) });
      }
      case "update_agent_artifact_lifecycle": {
        const parsed = agentControlToolSchemas.update_agent_artifact_lifecycle.parse(input);
        const result = context.kernel.updateArtifactLifecycle({
          ...parsed,
          ownerId: effectiveControlToolOwnerId(context, parsed.ownerId),
        });
        return stringifyToolResult({
          artifact: serializeArtifact(result.artifact),
          changed: result.changed,
          event: result.event ? serializeEvent(result.event) : null,
        });
      }
      case "send_agent_message": {
        const parsed = agentControlToolSchemas.send_agent_message.parse(input);
        const adapterId = parsed.adapterId ?? context.kernel.defaultAdapterIdForSession(parsed.sessionId);
        rejectSynchronousNestedRun(context, adapterId, parsed.sessionId);
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const requestId = parsed.requestId ?? `send-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        const result = await context.kernel.sendAgentMessage({
          ...parsed,
          ownerId,
          requestId,
          metadata: { ...(parsed.metadata ?? {}), disableSwiftBackedTools: true },
          mcpServers: buildControlRunMcpServers(context, {
            mode: parsed.mode,
            cwd: parsed.cwd,
            ownerId,
            requestId,
            clientId: parsed.clientId,
          }),
        });
        return stringifyToolResult({
          session: serializeSession(result.session),
          run: serializeRun(result.run),
          attempt: serializeAttempt(result.attempt),
          adapterSessionId: result.adapterSessionId,
          terminalStatus: result.terminalStatus,
          text: result.text,
        });
      }
      case "delegate_agent": {
        const parsed = agentControlToolSchemas.delegate_agent.parse(input);
        if (parsed.mode !== "spawn") {
          rejectSynchronousNestedRun(
            context,
            parsed.adapterId ?? parsed.defaultAdapterId ?? context.kernel.defaultAdapterIdForRun(parsed.parentRunId),
            parsed.mode === "continue" ? parsed.childSessionId : undefined
          );
        }
        const ownerId = effectiveControlToolOwnerId(context, parsed.ownerId);
        const requestId = parsed.requestId ?? `delegate-${parsed.mode}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        const result = await context.kernel.delegateAgent({
          ...parsed,
          ownerId,
          requestId,
          metadata: { ...(parsed.metadata ?? {}), disableSwiftBackedTools: true },
          mcpServers: buildControlRunMcpServers(context, {
            mode: parsed.runMode,
            cwd: parsed.cwd,
            ownerId,
            requestId,
            clientId: parsed.clientId,
          }),
        });
        return stringifyToolResult({
          delegation: serializeDelegation(result.delegation),
          childSession: serializeSession(result.childSession),
          childRun: serializeRun(result.childRun),
          childAttempt: result.childAttempt ? serializeAttempt(result.childAttempt) : null,
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
    }
  } catch (error) {
    return JSON.stringify({
      ok: false,
      error: {
        code: error instanceof z.ZodError ? "invalid_tool_input" : "control_tool_failed",
        message: error instanceof Error ? error.message : String(error),
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
  }
): Record<string, unknown>[] | undefined {
  if (!context.buildMcpServers) {
    return undefined;
  }
  const servers = context.buildMcpServers(input.mode, input.cwd, undefined, {
    ownerId: input.ownerId,
    requestId: input.requestId,
    clientId: input.clientId,
    protocolVersion: context.getProtocolVersion?.(),
    includeSwiftBackedTools: false,
  });
  // Direct control-created runs do not have a Swift ActiveRequest with an
  // onToolCall handler. Keep browser/stdio-independent MCPs available, but do
  // not expose omi-tools, whose execute_sql/semantic_search calls must be
  // answered by Swift-backed request routing.
  return servers.filter((server) => server.name !== "omi-tools");
}

function controlToolOwnerId(context: AgentControlToolContext): string {
  const ownerId = context.getOwnerId?.().trim();
  return ownerId || "desktop-local-user";
}

export function activeControlToolOwnerId(input: ActiveControlToolOwnerInput): string {
  const requestOwnerId = input.requestKey ? input.ownerIdForRequest?.(input.requestKey)?.trim() : undefined;
  if (requestOwnerId) {
    return requestOwnerId;
  }
  const attemptOwnerId = input.attemptId ? input.ownerIdForAttempt?.(input.attemptId)?.trim() : undefined;
  if (attemptOwnerId) {
    return attemptOwnerId;
  }
  const runOwnerId = input.runId ? input.ownerIdForRun?.(input.runId)?.trim() : undefined;
  if (runOwnerId) {
    return runOwnerId;
  }
  if (!input.allowFallbackOwner) {
    throw new Error("Owner-scoped control tools require active request, run, or attempt context");
  }
  const fallbackOwnerId = input.fallbackOwnerId?.trim();
  return fallbackOwnerId || "desktop-local-user";
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
      `Synchronous ${adapterId} control-tool runs are unavailable while that adapter is already executing; use spawn mode or retry after the current run finishes.`
    );
  }
}

function stringifyToolResult(payload: Record<string, unknown>): string {
  return JSON.stringify({ ok: true, ...payload });
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
  };
}

function serializeSession(session: AgentSession): Record<string, unknown> {
  return {
    omiSessionId: session.sessionId,
    ownerId: session.ownerId,
    agentDefinitionId: session.agentDefinitionId,
    title: session.title,
    status: session.status,
    surfaceKind: session.surfaceKind,
    externalRefKind: session.externalRefKind,
    externalRefId: session.externalRefId,
    legacyClientScope: session.legacyClientScope,
    legacySessionKey: session.legacySessionKey,
    defaultAdapterId: session.defaultAdapterId,
    defaultCwd: session.defaultCwd,
    modelProfile: session.modelProfile,
    metadata: parseJsonObject(session.metadataJson),
    createdAtMs: session.createdAtMs,
    updatedAtMs: session.updatedAtMs,
    lastActivityAtMs: session.lastActivityAtMs,
  };
}

function serializeRun(run: AgentRun): Record<string, unknown> {
  return {
    runId: run.runId,
    omiSessionId: run.sessionId,
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
    errorCode: run.errorCode,
    errorMessage: run.errorMessage,
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
  };
}

function serializeAttempt(attempt: RunAttempt): Record<string, unknown> {
  return {
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
    errorCode: attempt.errorCode,
    errorMessage: attempt.errorMessage,
    metadata: parseJsonObject(attempt.metadataJson),
    createdAtMs: attempt.createdAtMs,
    startedAtMs: attempt.startedAtMs,
    completedAtMs: attempt.completedAtMs,
    updatedAtMs: attempt.updatedAtMs,
  };
}

function serializeBinding(binding: AdapterBinding): Record<string, unknown> {
  return {
    bindingId: binding.bindingId,
    omiSessionId: binding.sessionId,
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

function serializeArtifact(artifact: AgentArtifact): Record<string, unknown> {
  return {
    artifactId: artifact.artifactId,
    omiSessionId: artifact.sessionId,
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
    createdAtMs: artifact.createdAtMs,
  };
}

function serializeEvent(event: AgentEvent): Record<string, unknown> {
  return {
    eventSeq: event.eventSeq,
    eventId: event.eventId,
    omiSessionId: event.sessionId,
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
