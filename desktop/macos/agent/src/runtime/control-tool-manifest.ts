export type AgentControlTimeoutClass = "normal" | "long";
export type AgentControlRiskTier = "low" | "medium" | "high";
export type AgentControlPrivacyTier = "low" | "local_private" | "sensitive";
export type AgentControlApprovalPolicy = "allow" | "user_approval" | "policy_grant";
export type AgentControlBundle =
  | "desktop.agent_control.read"
  | "desktop.agent_control.manage"
  | "desktop.context.local_read"
  | "desktop.context.screen_summary"
  | "desktop.context.screenshot_image"
  | "desktop.tasks.readwrite"
  | "desktop.artifacts.manage"
  | "desktop.automation.read"
  | "desktop.automation.act_dev_only"
  | "external.write_prepare"
  | "external.write_send";

export interface AgentControlManifestProperty {
  type: "string" | "number" | "boolean" | "object" | "array";
  description?: string;
  enum?: string[];
  items?: AgentControlManifestProperty;
  additionalProperties?: boolean;
}

export type AgentControlSurface = "desktopChat" | "realtimeHub";

export interface AgentControlMcpInputSchemaOptions {
  anyOf?: unknown[];
  allOf?: unknown[];
  oneOf?: unknown[];
  if?: unknown;
  then?: unknown;
}

export interface AgentControlManifestTool {
  name:
    | "list_agent_sessions"
    | "get_agent_run"
    | "build_desktop_awareness_snapshot"
    | "list_desktop_action_queue"
    | "get_desktop_open_loops"
    | "build_desktop_context_packet"
    | "route_desktop_intent"
    | "evaluate_desktop_tool_policy"
    | "create_desktop_dispatch"
    | "resolve_desktop_dispatch"
    | "cancel_agent_run"
    | "inspect_agent_artifacts"
    | "update_agent_artifact_lifecycle"
    | "send_agent_message"
    | "spawn_background_agent"
    | "delegate_agent";
  label: string;
  description: string;
  promptSnippet: string;
  promptGuidelines: string[];
  latency: "fast local" | "async background";
  surfaces: AgentControlSurface[];
  riskTier: AgentControlRiskTier;
  privacyTier: AgentControlPrivacyTier;
  approvalPolicy: AgentControlApprovalPolicy;
  bundles: readonly AgentControlBundle[];
  allowedSurfaces: readonly AgentControlSurface[];
  runtimePreconditions: string[];
  timeoutClass: AgentControlTimeoutClass;
  properties: Record<string, AgentControlManifestProperty>;
  required: string[];
  mcpInputSchemaOptions?: AgentControlMcpInputSchemaOptions;
}

const agentControlReadPolicy = {
  riskTier: "low",
  privacyTier: "local_private",
  approvalPolicy: "allow",
  bundles: ["desktop.agent_control.read"],
  allowedSurfaces: ["desktopChat", "realtimeHub"],
} as const;

const agentControlManagePolicy = {
  riskTier: "medium",
  privacyTier: "local_private",
  approvalPolicy: "policy_grant",
  bundles: ["desktop.agent_control.manage"],
  allowedSurfaces: ["desktopChat", "realtimeHub"],
} as const;

const artifactManagePolicy = {
  riskTier: "medium",
  privacyTier: "local_private",
  approvalPolicy: "policy_grant",
  bundles: ["desktop.artifacts.manage"],
  allowedSurfaces: ["desktopChat", "realtimeHub"],
} as const;

const contextReadPolicy = {
  riskTier: "low",
  privacyTier: "local_private",
  approvalPolicy: "allow",
  bundles: ["desktop.context.local_read"],
  allowedSurfaces: ["desktopChat", "realtimeHub"],
} as const;

const contextSensitivePolicy = {
  riskTier: "high",
  privacyTier: "sensitive",
  approvalPolicy: "user_approval",
  bundles: ["desktop.context.screen_summary"],
  allowedSurfaces: ["desktopChat", "realtimeHub"],
} as const;

export const agentControlCapabilityManifest = [
  {
    name: "list_agent_sessions",
    label: "List Agent Sessions",
    description: `List Omi-managed agent sessions from the local runtime kernel.

Use when the user asks what Omi agents/subagents are active, recent, failed, or attached to a surface.
Returns canonical Omi session IDs, latest/active run summaries, and adapter binding metadata.`,
    promptSnippet: "list_agent_sessions - List Omi-managed agent sessions and active runs",
    promptGuidelines: [
      "Use for current or recent kernel-backed Omi agents/subagents across chat, PTT/realtime, task chat, and any future migrated floating-pill sessions.",
      "Returns durable Omi session IDs, latest/active run summaries, and adapter binding metadata.",
    ],
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlReadPolicy,
    runtimePreconditions: ["Defaults ownerId to the active signed-in owner when omitted."],
    timeoutClass: "normal",
    properties: {
      ownerId: { type: "string", description: "Owner id to list. Defaults to the active signed-in owner." },
      status: { type: "string", enum: ["open", "archived", "closed"] },
      surfaceKind: {
        type: "string",
        enum: ["main_chat", "task_chat", "realtime", "delegated_agent", "background_agent", "floating_pill"],
        description: "Filter to a canonical surface kind.",
      },
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
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlReadPolicy,
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
    name: "build_desktop_awareness_snapshot",
    label: "Build Desktop Awareness Snapshot",
    description: "Build a local coordinator snapshot from kernel sessions, runs, dispatches, deliveries, candidates, and runtime health.",
    promptSnippet: "build_desktop_awareness_snapshot - Inspect local coordinator state",
    promptGuidelines: [
      "Use before routing new local work or summarizing open agent loops.",
      "Returns metadata and local state summaries, not raw transcripts or screenshot bytes.",
    ],
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlReadPolicy,
    runtimePreconditions: ["Defaults ownerId to the active signed-in owner when omitted."],
    timeoutClass: "normal",
    properties: {
      ownerId: { type: "string", description: "Owner id. Defaults to active owner." },
      limit: { type: "number", description: "Maximum rows per collection. Default 50, max 200." },
    },
    required: [],
  },
  {
    name: "list_desktop_action_queue",
    label: "List Desktop Action Queue",
    description: "Return the derived Desktop action queue from runs, dispatches, deliveries, candidates, legacy projections, and overrides.",
    promptSnippet: "list_desktop_action_queue - List pending local agent attention items",
    promptGuidelines: [
      "Use for approvals, failed runs, artifact review, stale work, and candidate review.",
      "The queue is derived and not persisted as authority.",
    ],
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlReadPolicy,
    runtimePreconditions: ["Defaults ownerId to active owner. Does not persist queue rows."],
    timeoutClass: "normal",
    properties: {
      ownerId: { type: "string", description: "Owner id. Defaults to active owner." },
      staleAfterMs: { type: "number", description: "Age after which active runs are considered stale." },
      limit: { type: "number", description: "Maximum queue items. Default 50, max 200." },
    },
    required: [],
  },
  {
    name: "get_desktop_open_loops",
    label: "Get Desktop Open Loops",
    description: "Summarize unresolved local coordinator loops: blocking dispatches, failed/stale runs, undelivered artifacts, and candidate reviews.",
    promptSnippet: "get_desktop_open_loops - Summarize unresolved local agent work",
    promptGuidelines: ["Use for quick status answers and voice status summaries."],
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlReadPolicy,
    runtimePreconditions: ["Defaults ownerId to active owner."],
    timeoutClass: "normal",
    properties: {
      ownerId: { type: "string", description: "Owner id. Defaults to active owner." },
      limit: { type: "number", description: "Maximum loops. Default 50, max 200." },
    },
    required: [],
  },
  {
    name: "build_desktop_context_packet",
    label: "Build Desktop Context Packet",
    description: "Persist a minimized DesktopContextPacket plus context-access audit rows from explicit selected snippets.",
    promptSnippet: "build_desktop_context_packet - Build scoped context for a local worker run",
    promptGuidelines: [
      "Use selected snippets with provenance, not full transcripts or screenshot image bytes.",
      "Requires a positive TTL and writes context-access audit rows.",
    ],
    latency: "fast local",
    surfaces: ["desktopChat"],
    ...contextSensitivePolicy,
    bundles: ["desktop.context.local_read", "desktop.context.screen_summary"],
    runtimePreconditions: ["Rejects missing TTL and raw screenshot image bytes."],
    timeoutClass: "normal",
    properties: {
      ownerId: { type: "string", description: "Owner id. Defaults to active owner." },
      sessionId: { type: "string", description: "Optional canonical session id scope." },
      runId: { type: "string", description: "Optional canonical run id scope." },
      surfaceKind: { type: "string", description: "Surface kind such as main_chat or task_chat." },
      objective: { type: "string", description: "Worker objective." },
      packetJson: { type: "object", description: "Selected context snippets and policy fields.", additionalProperties: true },
      ttlMs: { type: "number", description: "Positive TTL in milliseconds." },
      retentionClass: { type: "string", enum: ["ephemeral", "debug", "core"] },
    },
    required: ["surfaceKind", "objective", "packetJson", "ttlMs", "retentionClass"],
  },
  {
    name: "route_desktop_intent",
    label: "Route Desktop Intent",
    description: "Run deterministic local intent routing over action queue and reusable session candidates.",
    promptSnippet: "route_desktop_intent - Decide quick answer, resume, fork, delegate, dispatch, or new run",
    promptGuidelines: ["Use before creating a new run when existing local context may be relevant."],
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlReadPolicy,
    runtimePreconditions: ["Uses deterministic rules and returns an explanation."],
    timeoutClass: "normal",
    properties: {
      ownerId: { type: "string", description: "Owner id. Defaults to active owner." },
      utterance: { type: "string", description: "User request to route." },
      surfaceKind: { type: "string", description: "Current surface kind." },
      taskId: { type: "string", description: "Optional current task id." },
    },
    required: ["utterance", "surfaceKind"],
  },
  {
    name: "evaluate_desktop_tool_policy",
    label: "Evaluate Desktop Tool Policy",
    description: "Evaluate local coordinator policy for a tool/capability request without executing the tool.",
    promptSnippet: "evaluate_desktop_tool_policy - Check local capability policy",
    promptGuidelines: ["Use to explain why a sensitive local action needs dispatch or approval."],
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlReadPolicy,
    runtimePreconditions: ["Does not create grants or execute tools."],
    timeoutClass: "normal",
    properties: {
      toolName: { type: "string", description: "Optional tool name." },
      selectedBundles: {
        type: "array",
        description: "Selected capability bundles.",
        items: {
          type: "string",
          enum: [
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
          ],
        },
      },
      requestedBundles: {
        type: "array",
        description: "Optional explicit capability bundles being requested.",
        items: {
          type: "string",
          enum: [
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
          ],
        },
      },
      sql: { type: "string", description: "Optional SQL statement to classify." },
      operation: { type: "string", description: "Optional operation." },
      resourceRef: { type: "string", description: "Optional resource ref." },
    },
    required: ["selectedBundles"],
  },
  {
    name: "create_desktop_dispatch",
    label: "Create Desktop Dispatch",
    description: "Create a durable local DesktopCoordinatorDispatch for approvals, routing choices, artifact review, candidates, or sensitive context.",
    promptSnippet: "create_desktop_dispatch - Create a durable local decision item",
    promptGuidelines: ["Use when user attention or approval is required before crossing a boundary."],
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlManagePolicy,
    runtimePreconditions: ["Defaults ownerId to active owner. Source refs must match owner scope."],
    timeoutClass: "normal",
    properties: {
      ownerId: { type: "string", description: "Owner id. Defaults to active owner." },
      kind: { type: "string", enum: ["approval", "routing_choice", "failure_recovery", "artifact_review", "memory_candidate", "task_candidate", "external_draft", "screen_context"] },
      priority: { type: "number", description: "Priority integer." },
      title: { type: "string", description: "Short title." },
      decisionPrompt: { type: "string", description: "Exact decision prompt." },
      payload: { type: "object", description: "Small structured payload.", additionalProperties: true },
    },
    required: ["kind", "priority", "title", "decisionPrompt"],
  },
  {
    name: "resolve_desktop_dispatch",
    label: "Resolve Desktop Dispatch",
    description: "Resolve or cancel a pending local DesktopCoordinatorDispatch, optionally creating a scoped allow grant for an explicit approval.",
    promptSnippet: "resolve_desktop_dispatch - Resolve a durable local decision item",
    promptGuidelines: ["Use only for explicit user approval/denial/cancel decisions."],
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlManagePolicy,
    runtimePreconditions: [
      "Defaults ownerId to active owner and refuses expired dispatches.",
      "When grant is supplied for a resolved approval, grant creation and approval.resolved event append happen in one transaction.",
    ],
    timeoutClass: "normal",
    properties: {
      dispatchId: { type: "string", description: "Dispatch id." },
      ownerId: { type: "string", description: "Owner guard. Defaults to active owner." },
      status: { type: "string", enum: ["resolved", "cancelled"] },
      resolvedBy: { type: "string", description: "Resolver id, usually user." },
      resolution: { type: "object", description: "Resolution payload.", additionalProperties: true },
      grant: { type: "object", description: "Optional scoped grant to create for an explicit allow resolution.", additionalProperties: true },
    },
    required: ["dispatchId", "status"],
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
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlManagePolicy,
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
    description: `Inspect canonical artifact metadata for an Omi agent artifact, session, run, or attempt.

Returns metadata and references only. It does not read arbitrary artifact contents.`,
    promptSnippet: "inspect_agent_artifacts - Inspect Omi agent artifact metadata",
    promptGuidelines: [
      "Returns artifact references and metadata only.",
      "Use after get_agent_run when the user asks what files or outputs an agent produced.",
    ],
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlReadPolicy,
    runtimePreconditions: [
      "Requires at least one of artifactId, sessionId, runId, or attemptId.",
      "Defaults ownerId to the active signed-in owner when omitted and rejects selectors outside that owner.",
    ],
    timeoutClass: "normal",
    properties: {
      artifactId: { type: "string", description: "Canonical Omi artifact_id." },
      sessionId: { type: "string", description: "Canonical Omi session_id." },
      runId: { type: "string", description: "Canonical Omi run_id." },
      attemptId: { type: "string", description: "Canonical Omi attempt_id." },
      ownerId: { type: "string", description: "Owner guard. Defaults to the active signed-in owner." },
      role: { type: "string", enum: ["input", "result", "checkpoint", "tool_output", "log", "other"] },
      limit: { type: "number", description: "Maximum artifacts to return. Default 50, max 200." },
    },
    required: [],
    mcpInputSchemaOptions: {
      anyOf: [
        { required: ["artifactId"] },
        { required: ["sessionId"] },
        { required: ["runId"] },
        { required: ["attemptId"] },
      ],
    },
  },
  {
    name: "update_agent_artifact_lifecycle",
    label: "Update Agent Artifact Lifecycle",
    description: `Update metadata-only lifecycle state for one canonical Omi agent artifact.

This only records artifact metadata state and ordered kernel events. It does not open files, delete files, retain blobs, or read artifact contents.`,
    promptSnippet: "update_agent_artifact_lifecycle - Mark an Omi agent artifact retained, dismissed, or opened",
    promptGuidelines: [
      "Use to mark artifact metadata as retained, dismissed, or opened after a user-visible artifact decision.",
      "Pass sessionId, runId, or attemptId when available as a scope guard.",
      "This never reads artifact contents and has no OS side effects.",
    ],
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...artifactManagePolicy,
    runtimePreconditions: [
      "Requires artifactId.",
      "Defaults ownerId to the active signed-in owner when omitted and rejects artifacts outside that owner.",
      "Optional sessionId, runId, and attemptId must match the artifact scope.",
    ],
    timeoutClass: "normal",
    properties: {
      artifactId: { type: "string", description: "Canonical Omi artifact_id." },
      state: { type: "string", enum: ["retained", "dismissed", "opened"], description: "Target metadata lifecycle state." },
      sessionId: { type: "string", description: "Optional canonical Omi session_id scope guard." },
      runId: { type: "string", description: "Optional canonical Omi run_id scope guard." },
      attemptId: { type: "string", description: "Optional canonical Omi attempt_id scope guard." },
      ownerId: { type: "string", description: "Owner guard. Defaults to the active signed-in owner." },
      reason: { type: "string", description: "Optional short reason for the lifecycle event." },
      metadata: { type: "object", description: "Small structured metadata for the lifecycle event.", additionalProperties: true },
    },
    required: ["artifactId", "state"],
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
    riskTier: "medium",
    privacyTier: "local_private",
    approvalPolicy: "policy_grant",
    bundles: ["desktop.agent_control.manage"],
    allowedSurfaces: ["desktopChat"],
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
      requestId: { type: "string", description: "Optional caller-provided request correlation id." },
      clientId: { type: "string", description: "Logical caller id. Defaults to omi-control-tools." },
      metadata: { type: "object", description: "Small structured metadata for this run.", additionalProperties: true },
    },
    required: ["sessionId", "prompt"],
  },
  {
    name: "spawn_background_agent",
    label: "Spawn Background Agent",
    description: `Create a canonical Omi-managed background agent session/run without requiring a parent run.

Use this for top-level chat or realtime requests that need visible background work. UI surfaces may project the returned canonical session/run into a floating pill, but the runtime remains the source of truth.`,
    promptSnippet: "spawn_background_agent - Start a canonical top-level background agent",
    promptGuidelines: [
      "Use for top-level background work when there is no parent run to pass to delegate_agent.",
      "Returns canonical session and run handles immediately; inspect progress with list_agent_sessions or get_agent_run.",
      "Do not use this to create UI-owned ChatProvider runtime state.",
    ],
    latency: "async background",
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlManagePolicy,
    runtimePreconditions: [
      "Defaults ownerId to the active signed-in owner when omitted.",
      "Creates a canonical background_agent session/run and executes it asynchronously.",
    ],
    timeoutClass: "long",
    properties: {
      prompt: { type: "string", description: "Self-contained background-agent task prompt." },
      title: { type: "string", description: "Optional visible session title." },
      surfaceKind: { type: "string", description: "Optional session surface kind. Default background_agent." },
      externalRefKind: { type: "string", description: "Optional external reference kind for UI projection." },
      externalRefId: { type: "string", description: "Optional external reference id for UI projection." },
      ownerId: { type: "string", description: "Owner id. Defaults to the active signed-in owner." },
      adapterId: { type: "string", description: "Optional adapter override." },
      defaultAdapterId: { type: "string", description: "Optional session default adapter." },
      cwd: { type: "string", description: "Optional working directory." },
      model: { type: "string", description: "Optional model override." },
      mode: { type: "string", enum: ["ask", "act"], description: "Run mode. Default act." },
      requestId: { type: "string", description: "Optional caller-provided request correlation id." },
      clientId: { type: "string", description: "Logical caller id. Defaults to omi-control-tools." },
      metadata: { type: "object", description: "Small structured metadata for this run.", additionalProperties: true },
    },
    required: ["prompt"],
  },
  {
    name: "delegate_agent",
    label: "Delegate Agent",
    description: `Create or continue a distinct delegated child agent session linked to a parent run.

Supports call, spawn, and continue modes. Child context is intentionally minimal: objective plus optional concise context. Spawn returns canonical child handles immediately; call and continue return a structured child result without the full transcript. This does not create or manage floating pill UI.`,
    promptSnippet: "delegate_agent - Create or continue a canonical Omi child agent",
    promptGuidelines: [
      "Use call for a structured child result, spawn for immediate canonical child handles, and continue for another run in an existing child session.",
      "Use spawn_agent instead when top-level work should also be shown in the floating-bar pill UI.",
      "Pass a concise objective and optional short context; do not pass full transcripts by default.",
    ],
    latency: "async background",
    surfaces: ["desktopChat"],
    riskTier: "medium",
    privacyTier: "local_private",
    approvalPolicy: "policy_grant",
    bundles: ["desktop.agent_control.manage"],
    allowedSurfaces: ["desktopChat"],
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
      requestId: { type: "string", description: "Optional caller-provided request correlation id." },
      clientId: { type: "string", description: "Logical caller id. Defaults to omi-control-tools." },
      maxDepth: { type: "number", description: "Maximum delegation depth for this call. Default 3, hard max 5." },
      maxBudgetUsd: { type: "number", description: "Per-delegation budget guard. Default 5, hard max 10." },
      metadata: { type: "object", description: "Small structured metadata for the child run.", additionalProperties: true },
    },
    required: ["mode", "parentRunId", "objective"],
    mcpInputSchemaOptions: {
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
      if (property.type === "array" && property.items) {
        const itemSchema: Record<string, unknown> = {
          type: property.items.type,
        };
        if (property.items.description) itemSchema.description = property.items.description;
        if (property.items.enum) itemSchema.enum = property.items.enum;
        schema.items = itemSchema;
      }
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
  };
}
