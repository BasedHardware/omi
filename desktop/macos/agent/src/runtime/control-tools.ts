import { z } from "zod";
import type { AgentArtifact, AgentDelegation, AgentEvent, AgentRun, AgentSession, AdapterBinding, RunAttempt } from "./types.js";
import { AgentRuntimeKernel } from "./kernel.js";

const sessionStatusSchema = z.enum(["open", "archived", "closed"]);
const artifactRoleSchema = z.enum(["input", "result", "checkpoint", "tool_output", "log", "other"]);
const runModeSchema = z.enum(["ask", "act"]);
const delegationModeSchema = z.enum(["call", "spawn", "continue"]);

const listAgentSessionsSchema = z.object({
  ownerId: z.string().min(1).default("desktop-local-user"),
  status: sessionStatusSchema.optional(),
  surfaceKind: z.string().min(1).optional(),
  limit: z.coerce.number().int().positive().max(200).default(50),
  beforeUpdatedAtMs: z.coerce.number().int().positive().optional(),
});

const getAgentRunSchema = z.object({
  runId: z.string().min(1),
  includeEvents: z.boolean().default(true),
  eventLimit: z.coerce.number().int().positive().max(500).default(100),
});

const cancelAgentRunSchema = z.object({
  runId: z.string().min(1),
});

const inspectAgentArtifactsSchema = z
  .object({
    sessionId: z.string().min(1).optional(),
    runId: z.string().min(1).optional(),
    attemptId: z.string().min(1).optional(),
    role: artifactRoleSchema.optional(),
    limit: z.coerce.number().int().positive().max(200).default(50),
  })
  .refine((value) => value.sessionId || value.runId || value.attemptId, {
    message: "Provide sessionId, runId, or attemptId",
  });

const sendAgentMessageSchema = z.object({
  sessionId: z.string().min(1),
  ownerId: z.string().min(1).default("desktop-local-user"),
  prompt: z.string().min(1),
  mode: runModeSchema.default("ask"),
  adapterId: z.string().min(1).optional(),
  cwd: z.string().min(1).optional(),
  model: z.string().min(1).optional(),
  requestId: z.string().min(1).optional(),
  clientId: z.string().min(1).default("omi-control-tools"),
  metadata: z.record(z.string(), z.unknown()).default({}),
});

const delegateAgentSchema = z.object({
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
});

export const agentControlToolSchemas = {
  list_agent_sessions: listAgentSessionsSchema,
  get_agent_run: getAgentRunSchema,
  cancel_agent_run: cancelAgentRunSchema,
  inspect_agent_artifacts: inspectAgentArtifactsSchema,
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

export const agentControlToolDefinitions: AgentControlToolDefinition[] = [
  {
    name: "list_agent_sessions",
    description: `List Omi-managed agent sessions from the local runtime kernel.

Use when the user asks what Omi agents/subagents are active, recent, failed, or attached to a surface.
Returns canonical Omi session IDs, latest/active run summaries, and adapter binding metadata.`,
    inputSchema: {
      type: "object",
      properties: {
        ownerId: { type: "string", description: "Owner id to list. Defaults to the local desktop user." },
        status: { type: "string", enum: ["open", "archived", "closed"] },
        surfaceKind: { type: "string", description: "Filter to a surface kind such as main_chat, task_chat, or floating_pill." },
        limit: { type: "number", description: "Maximum sessions to return. Default 50, max 200." },
        beforeUpdatedAtMs: { type: "number", description: "Pagination cursor: only sessions updated before this epoch-ms timestamp." },
      },
      required: [],
    },
  },
  {
    name: "get_agent_run",
    description: `Inspect one canonical Omi agent run.

Use a runId returned by list_agent_sessions or a correlated Omi response. Returns the run, session, attempts, adapter bindings, artifact metadata, and optionally events.`,
    inputSchema: {
      type: "object",
      properties: {
        runId: { type: "string", description: "Canonical Omi run_id." },
        includeEvents: { type: "boolean", description: "Include ordered kernel events. Default true." },
        eventLimit: { type: "number", description: "Maximum events to return. Default 100, max 500." },
      },
      required: ["runId"],
    },
  },
  {
    name: "cancel_agent_run",
    description: `Request cancellation for one canonical Omi agent run through the runtime kernel.

Use when the user asks to stop a running Omi agent/subagent. Returns whether cancellation was accepted, dispatched to the adapter, and acknowledged by the adapter.`,
    inputSchema: {
      type: "object",
      properties: {
        runId: { type: "string", description: "Canonical Omi run_id to cancel." },
      },
      required: ["runId"],
    },
  },
  {
    name: "inspect_agent_artifacts",
    description: `Inspect canonical artifact metadata for an Omi agent session, run, or attempt.

Returns metadata and references only. It does not read arbitrary artifact contents.`,
    inputSchema: {
      type: "object",
      properties: {
        sessionId: { type: "string", description: "Canonical Omi session_id." },
        runId: { type: "string", description: "Canonical Omi run_id." },
        attemptId: { type: "string", description: "Canonical Omi attempt_id." },
        role: { type: "string", enum: ["input", "result", "checkpoint", "tool_output", "log", "other"] },
        limit: { type: "number", description: "Maximum artifacts to return. Default 50, max 200." },
      },
      required: [],
    },
  },
  {
    name: "send_agent_message",
    description: `Send a follow-up message to an existing canonical Omi agent session.

Creates a new run in that session through the runtime kernel. Use this for multi-turn conversations with Omi-managed agents when you already have an omiSessionId.`,
    inputSchema: {
      type: "object",
      properties: {
        sessionId: { type: "string", description: "Canonical Omi session_id to continue." },
        ownerId: { type: "string", description: "Owner id. Defaults to the local desktop user." },
        prompt: { type: "string", description: "The follow-up message." },
        mode: { type: "string", enum: ["ask", "act"], description: "Run mode. Default ask." },
        adapterId: { type: "string", description: "Optional adapter override." },
        cwd: { type: "string", description: "Optional working directory override." },
        model: { type: "string", description: "Optional model override." },
        requestId: { type: "string", description: "Optional caller-provided idempotent request id." },
        clientId: { type: "string", description: "Logical caller id. Defaults to omi-control-tools." },
        metadata: { type: "object", description: "Small structured metadata for this run." },
      },
      required: ["sessionId", "prompt"],
    },
  },
  {
    name: "delegate_agent",
    description: `Create or continue a distinct delegated child agent session linked to a parent run.

Supports call, spawn, and continue modes. Child context is intentionally minimal: objective plus optional concise context. Spawn returns child handles immediately; call and continue return a structured child result without the full transcript.`,
    inputSchema: {
      type: "object",
      properties: {
        mode: { type: "string", enum: ["call", "spawn", "continue"] },
        parentRunId: { type: "string", description: "Canonical parent Omi run_id." },
        objective: { type: "string", description: "Delegated objective for the child agent." },
        context: { type: "string", description: "Optional concise context, not a full transcript." },
        ownerId: { type: "string", description: "Optional owner guard for the parent run." },
        childSessionId: { type: "string", description: "Required for continue mode; optional only to resume a known child." },
        childSurfaceKind: { type: "string", description: "Child session surface kind. Default delegated_agent." },
        childExternalRefKind: { type: "string", description: "Optional child external reference kind." },
        childExternalRefId: { type: "string", description: "Optional child external reference id." },
        childTitle: { type: "string", description: "Optional title for a newly created child session." },
        adapterId: { type: "string", description: "Optional adapter override." },
        defaultAdapterId: { type: "string", description: "Optional child session default adapter." },
        cwd: { type: "string", description: "Optional working directory." },
        model: { type: "string", description: "Optional model override." },
        runMode: { type: "string", enum: ["ask", "act"], description: "Child run mode. Default ask." },
        requestId: { type: "string", description: "Optional caller-provided idempotent request id." },
        clientId: { type: "string", description: "Logical caller id. Defaults to omi-control-tools." },
        maxDepth: { type: "number", description: "Maximum delegation depth for this call. Default 3, hard max 5." },
        maxBudgetUsd: { type: "number", description: "Per-delegation budget guard. Default 5, hard max 10." },
        metadata: { type: "object", description: "Small structured metadata for the child run." },
      },
      required: ["mode", "parentRunId", "objective"],
    },
  },
];

export interface AgentControlToolContext {
  kernel: AgentRuntimeKernel;
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
        const sessions = context.kernel.listSessions(parsed);
        return stringifyToolResult({ sessions: sessions.map(serializeSessionSummary) });
      }
      case "get_agent_run": {
        const parsed = agentControlToolSchemas.get_agent_run.parse(input);
        const details = context.kernel.getRun(parsed);
        return stringifyToolResult(serializeRunDetails(details));
      }
      case "cancel_agent_run": {
        const parsed = agentControlToolSchemas.cancel_agent_run.parse(input);
        const cancellation = await context.kernel.cancelRun(parsed.runId);
        const details = context.kernel.getRun({ runId: parsed.runId, includeEvents: true, eventLimit: 100 });
        return stringifyToolResult({
          cancellation,
          run: serializeRun(details.run),
          attempts: details.attempts.map(serializeAttempt),
        });
      }
      case "inspect_agent_artifacts": {
        const parsed = agentControlToolSchemas.inspect_agent_artifacts.parse(input);
        const artifacts = context.kernel.inspectArtifacts(parsed);
        return stringifyToolResult({ artifacts: artifacts.map(serializeArtifact) });
      }
      case "send_agent_message": {
        const parsed = agentControlToolSchemas.send_agent_message.parse(input);
        const result = await context.kernel.sendAgentMessage({
          ...parsed,
          requestId: parsed.requestId ?? `send-${Date.now()}-${Math.random().toString(16).slice(2)}`,
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
        const result = await context.kernel.delegateAgent({
          ...parsed,
          requestId: parsed.requestId ?? `delegate-${parsed.mode}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
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
