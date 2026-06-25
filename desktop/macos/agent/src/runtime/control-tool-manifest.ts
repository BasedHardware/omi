export type AgentControlTimeoutClass = "normal" | "long";

export interface AgentControlManifestProperty {
  type: "string" | "number" | "boolean" | "object";
  description?: string;
  enum?: string[];
  additionalProperties?: boolean;
}

export interface AgentControlManifestTool {
  name:
    | "list_agent_sessions"
    | "get_agent_run"
    | "cancel_agent_run"
    | "inspect_agent_artifacts"
    | "send_agent_message"
    | "delegate_agent";
  label: string;
  description: string;
  promptSnippet: string;
  promptGuidelines: string[];
  latency: "fast local" | "async background";
  surfaces: ["desktopChat"];
  runtimePreconditions: string[];
  timeoutClass: AgentControlTimeoutClass;
  properties: Record<string, AgentControlManifestProperty>;
  required: string[];
  jsonSchemaOptions?: Record<string, unknown>;
}

export const agentControlCapabilityManifest = [
  {
    name: "list_agent_sessions",
    label: "List Agent Sessions",
    description: `List Omi-managed agent sessions from the local runtime kernel.

Use when the user asks what Omi agents/subagents are active, recent, failed, or attached to a surface.
Returns canonical Omi session IDs, latest/active run summaries, and adapter binding metadata.`,
    promptSnippet: "list_agent_sessions - List Omi-managed agent sessions and active runs",
    promptGuidelines: [
      "Use for current or recent kernel-backed Omi agents/subagents across main chat, task chat, and any future migrated floating-pill sessions.",
      "Returns durable Omi session IDs, latest/active run summaries, and adapter binding metadata.",
    ],
    latency: "fast local",
    surfaces: ["desktopChat"],
    runtimePreconditions: ["Defaults ownerId to the active signed-in owner when omitted."],
    timeoutClass: "normal",
    properties: {
      ownerId: { type: "string", description: "Owner id to list. Defaults to the active signed-in owner." },
      status: { type: "string", enum: ["open", "archived", "closed"] },
      surfaceKind: { type: "string", description: "Filter to a surface kind such as main_chat, task_chat, or floating_pill." },
      limit: { type: "number", description: "Maximum sessions to return. Default 50, max 200." },
      beforeUpdatedAtMs: { type: "number", description: "Pagination cursor: only sessions updated before this epoch-ms timestamp." },
    },
    required: [],
  },
  {
    name: "get_agent_run",
    label: "Get Agent Run",
    description: `Inspect one canonical Omi agent run.

Use a runId returned by list_agent_sessions or a correlated Omi response. Returns the run, session, attempts, adapter bindings, artifact metadata, and optionally events.`,
    promptSnippet: "get_agent_run - Inspect one Omi agent run",
    promptGuidelines: [
      "Use a runId from list_agent_sessions or a correlated Omi result.",
      "Returns the run, attempts, adapter bindings, events, and artifact metadata.",
    ],
    latency: "fast local",
    surfaces: ["desktopChat"],
    runtimePreconditions: [
      "Requires a canonical Omi run_id.",
      "Defaults ownerId to the active signed-in owner when omitted and rejects runs outside that owner.",
    ],
    timeoutClass: "normal",
    properties: {
      runId: { type: "string", description: "Canonical Omi run_id." },
      ownerId: { type: "string", description: "Owner guard. Defaults to the active signed-in owner." },
      includeEvents: { type: "boolean", description: "Include ordered kernel events. Default true." },
      eventLimit: { type: "number", description: "Maximum events to return. Default 100, max 500." },
    },
    required: ["runId"],
  },
  {
    name: "cancel_agent_run",
    label: "Cancel Agent Run",
    description: `Request cancellation for one canonical Omi agent run through the runtime kernel.

Use when the user asks to stop a running Omi agent/subagent. Returns whether cancellation was accepted, dispatched to the adapter, and acknowledged by the adapter.`,
    promptSnippet: "cancel_agent_run - Stop a running Omi agent",
    promptGuidelines: [
      "Use when the user asks to stop a running Omi agent/subagent.",
      "Returns whether cancellation was accepted, dispatched, and acknowledged.",
    ],
    latency: "fast local",
    surfaces: ["desktopChat"],
    runtimePreconditions: [
      "Requires a canonical Omi run_id.",
      "Defaults ownerId to the active signed-in owner when omitted and rejects runs outside that owner.",
    ],
    timeoutClass: "normal",
    properties: {
      runId: { type: "string", description: "Canonical Omi run_id to cancel." },
      ownerId: { type: "string", description: "Owner guard. Defaults to the active signed-in owner." },
    },
    required: ["runId"],
  },
  {
    name: "inspect_agent_artifacts",
    label: "Inspect Agent Artifacts",
    description: `Inspect canonical artifact metadata for an Omi agent session, run, or attempt.

Returns metadata and references only. It does not read arbitrary artifact contents.`,
    promptSnippet: "inspect_agent_artifacts - Inspect Omi agent artifact metadata",
    promptGuidelines: [
      "Returns artifact references and metadata only.",
      "Use after get_agent_run when the user asks what files or outputs an agent produced.",
    ],
    latency: "fast local",
    surfaces: ["desktopChat"],
    runtimePreconditions: [
      "Requires at least one of sessionId, runId, or attemptId.",
      "Defaults ownerId to the active signed-in owner when omitted and rejects selectors outside that owner.",
    ],
    timeoutClass: "normal",
    properties: {
      sessionId: { type: "string", description: "Canonical Omi session_id." },
      runId: { type: "string", description: "Canonical Omi run_id." },
      attemptId: { type: "string", description: "Canonical Omi attempt_id." },
      ownerId: { type: "string", description: "Owner guard. Defaults to the active signed-in owner." },
      role: { type: "string", enum: ["input", "result", "checkpoint", "tool_output", "log", "other"] },
      limit: { type: "number", description: "Maximum artifacts to return. Default 50, max 200." },
    },
    required: [],
    jsonSchemaOptions: {
      anyOf: [
        { required: ["sessionId"] },
        { required: ["runId"] },
        { required: ["attemptId"] },
      ],
    },
  },
  {
    name: "send_agent_message",
    label: "Send Agent Message",
    description: `Send a follow-up message to an existing canonical Omi agent session.

Creates a new run in that session through the runtime kernel. Use this for multi-turn conversations with Omi-managed agents when you already have a sessionId.`,
    promptSnippet: "send_agent_message - Continue an Omi-managed agent session",
    promptGuidelines: [
      "Use when continuing a multi-turn conversation with an Omi-managed agent by sessionId.",
      "Creates a new run in the existing session; do not use it to create a delegated child.",
    ],
    latency: "async background",
    surfaces: ["desktopChat"],
    runtimePreconditions: [
      "Defaults ownerId to the active signed-in owner when omitted.",
      "Rejects synchronous nested runs when the selected adapter is already executing for the session or has no capacity.",
    ],
    timeoutClass: "long",
    properties: {
      sessionId: { type: "string", description: "Canonical Omi session_id to continue." },
      ownerId: { type: "string", description: "Owner id. Defaults to the active signed-in owner." },
      prompt: { type: "string", description: "The follow-up message." },
      mode: { type: "string", enum: ["ask", "act"], description: "Run mode. Default ask." },
      adapterId: { type: "string", description: "Optional adapter override." },
      cwd: { type: "string", description: "Optional working directory override." },
      model: { type: "string", description: "Optional model override." },
      requestId: { type: "string", description: "Optional caller-provided idempotent request id." },
      clientId: { type: "string", description: "Logical caller id. Defaults to omi-control-tools." },
      metadata: { type: "object", description: "Small structured metadata for this run.", additionalProperties: true },
    },
    required: ["sessionId", "prompt"],
  },
  {
    name: "delegate_agent",
    label: "Delegate Agent",
    description: `Create or continue a distinct delegated child agent session linked to a parent run.

Supports call, spawn, and continue modes. Child context is intentionally minimal: objective plus optional concise context. Spawn returns canonical child handles immediately; call and continue return a structured child result without the full transcript. This does not create or manage floating pill UI.`,
    promptSnippet: "delegate_agent - Create or continue a canonical Omi child agent",
    promptGuidelines: [
      "Use call for a structured child result, spawn for immediate canonical child handles, and continue for another run in an existing child session.",
      "Use spawn_agent instead when the user wants a visible floating-bar background agent pill.",
      "Pass a concise objective and optional short context; do not pass full transcripts by default.",
    ],
    latency: "async background",
    surfaces: ["desktopChat"],
    runtimePreconditions: [
      "Requires childSessionId when mode is continue.",
      "Rejects synchronous nested call/continue runs when the selected adapter is already executing for the child session or has no capacity.",
      "Spawn mode returns canonical child handles immediately and does not wait for completion; it does not create floating pill UI.",
    ],
    timeoutClass: "long",
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
      metadata: { type: "object", description: "Small structured metadata for the child run.", additionalProperties: true },
    },
    required: ["mode", "parentRunId", "objective"],
    jsonSchemaOptions: {
      allOf: [
        {
          if: { properties: { mode: { const: "continue" } }, required: ["mode"] },
          then: { required: ["childSessionId"] },
        },
      ],
    },
  },
] as const satisfies AgentControlManifestTool[];

export type AgentControlManifestToolName = (typeof agentControlCapabilityManifest)[number]["name"];

export function agentControlInputSchema(tool: AgentControlManifestTool): Record<string, unknown> {
  const properties = Object.fromEntries(
    Object.entries(tool.properties).map(([name, property]) => {
      const schema: Record<string, unknown> = {
        type: property.type,
      };
      if (property.description) schema.description = property.description;
      if (property.enum) schema.enum = property.enum;
      if (property.type === "object" && property.additionalProperties !== undefined) {
        schema.additionalProperties = property.additionalProperties;
      }
      return [name, schema];
    })
  );
  return {
    type: "object",
    properties,
    required: tool.required,
    ...tool.jsonSchemaOptions,
  };
}
