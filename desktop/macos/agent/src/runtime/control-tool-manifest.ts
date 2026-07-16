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
    | "read_tool_output"
    | "search_tool_output"
    | "update_agent_artifact_lifecycle"
    | "send_agent_message"
    | "spawn_background_agent"
    | "spawn_agent"
    | "run_agent_and_wait"
    | "set_desktop_attention_override";
  label: string;
  description: string;
  promptSnippet: string;
  promptGuidelines: string[];
  capabilityDoc: {
    title: string;
    summary: string;
    bullets: string[];
  };
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

function controlDoc(label: string, summary: string, bullets: string[]) {
  return { title: label, summary, bullets };
}

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
Returns canonical session/run summaries plus task_agents and floating_agent_pills projections.`,
    promptSnippet: "list_agent_sessions - List Omi-managed agent sessions and active runs",
    promptGuidelines: [
      "Use for current or recent kernel-backed Omi agents/subagents across chat, PTT/realtime, task chat, and floating-bar pills.",
      "Returns task_agents and floating_agent_pills alongside canonical session summaries.",
      "For a prior child agent's final answer, do not infer run completion from session status or restrict discovery to status='open'. List recent sessions, then call get_agent_run with the returned runId and answer from run.finalText without exposing the internal id.",
    ],
    capabilityDoc: controlDoc(
      "List Agent Sessions",
      "List Omi-managed agent sessions from the local runtime kernel.",
      [
        "Use for current or recent kernel-backed Omi agents/subagents across chat, PTT/realtime, task chat, and floating-bar pills.",
        "Returns task_agents and floating_agent_pills alongside canonical session summaries.",
      ],
    ),
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
        enum: ["main_chat", "task_chat", "realtime", "delegated_agent", "background_agent", "floating_bar", "floating_pill"],
        description: "Optional surface hint. background_agent and delegated_agent discover recent child sessions across concrete surfaces.",
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
      "For a completed child, use run.finalText to answer the user and keep the internal runId out of the user-visible response.",
    ],
    capabilityDoc: controlDoc(
      "Get Agent Run",
      "Inspect one canonical Omi agent run.",
      [
        "Use a runId from list_agent_sessions or a correlated Omi result.",
        "Returns the run, attempts, adapter bindings, events, and artifact metadata.",
      ],
    ),
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
    capabilityDoc: controlDoc(
      "Build Desktop Awareness Snapshot",
      "Build a local coordinator snapshot from kernel sessions, runs, dispatches, deliveries, candidates, and runtime health.",
      [
        "Use before routing new local work or summarizing open agent loops.",
        "Returns metadata and local state summaries, not raw transcripts or screenshot bytes.",
      ],
    ),
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
    capabilityDoc: controlDoc(
      "List Desktop Action Queue",
      "Return the derived Desktop action queue from runs, dispatches, deliveries, candidates, legacy projections, and overrides.",
      [
        "Use for approvals, failed runs, artifact review, stale work, and candidate review.",
        "The queue is derived and not persisted as authority.",
      ],
    ),
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
    capabilityDoc: controlDoc(
      "Get Desktop Open Loops",
      "Summarize unresolved local coordinator loops: blocking dispatches, failed/stale runs, undelivered artifacts, and candidate reviews.",
      ["Use for quick status answers and voice status summaries."],
    ),
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
    capabilityDoc: controlDoc(
      "Build Desktop Context Packet",
      "Persist a minimized DesktopContextPacket plus context-access audit rows from explicit selected snippets.",
      [
        "Use selected snippets with provenance, not full transcripts or screenshot image bytes.",
        "Requires a positive TTL and writes context-access audit rows.",
      ],
    ),
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
    capabilityDoc: controlDoc(
      "Route Desktop Intent",
      "Run deterministic local intent routing over action queue and reusable session candidates.",
      ["Use before creating a new run when existing local context may be relevant."],
    ),
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
    capabilityDoc: controlDoc(
      "Evaluate Desktop Tool Policy",
      "Evaluate local coordinator policy for a tool/capability request without executing the tool.",
      ["Use to explain why a sensitive local action needs dispatch or approval."],
    ),
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
    capabilityDoc: controlDoc(
      "Create Desktop Dispatch",
      "Create a durable local DesktopCoordinatorDispatch for approvals, routing choices, artifact review, candidates, or sensitive context.",
      ["Use when user attention or approval is required before crossing a boundary."],
    ),
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
      recommendedDefault: { type: "string", description: "Optional recommended default decision label." },
      sourceSessionId: { type: "string", description: "Optional source Omi session_id scope guard." },
      sourceRunId: { type: "string", description: "Optional source Omi run_id scope guard." },
      sourceAttemptId: { type: "string", description: "Optional source Omi attempt_id scope guard." },
      sourceArtifactId: { type: "string", description: "Optional source Omi artifact_id scope guard." },
      capability: { type: "string", description: "Capability being requested, e.g. desktop.context.screenshot_image." },
      operation: { type: "string", description: "Operation being requested, e.g. get_screenshot." },
      resourceRef: { type: "string", description: "Resource reference for scoped approval." },
      payload: { type: "object", description: "Small structured payload.", additionalProperties: true },
      expiresAtMs: { type: "number", description: "Optional epoch-ms expiration for the decision item." },
    },
    required: ["kind", "priority", "title", "decisionPrompt"],
  },
  {
    name: "resolve_desktop_dispatch",
    label: "Resolve Desktop Dispatch",
    description: "Resolve or cancel a pending local DesktopCoordinatorDispatch, optionally creating a scoped allow grant for an explicit approval.",
    promptSnippet: "resolve_desktop_dispatch - Resolve a durable local decision item",
    promptGuidelines: ["Use only for explicit user approval/denial/cancel decisions."],
    capabilityDoc: controlDoc(
      "Resolve Desktop Dispatch",
      "Resolve or cancel a pending local DesktopCoordinatorDispatch, optionally creating a scoped allow grant for an explicit approval.",
      ["Use only for explicit user approval/denial/cancel decisions."],
    ),
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
    capabilityDoc: controlDoc(
      "Cancel Agent Run",
      "Request cancellation for one canonical Omi agent run through the runtime kernel.",
      [
        "Use when the user asks to stop a running Omi agent/subagent.",
        "Returns whether cancellation was accepted, dispatched, and acknowledged.",
      ],
    ),
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
    capabilityDoc: controlDoc(
      "Inspect Agent Artifacts",
      "Inspect canonical artifact metadata for an Omi agent artifact, session, run, or attempt.",
      [
        "Returns artifact references and metadata only.",
        "Use after get_agent_run when the user asks what files or outputs an agent produced.",
      ],
    ),
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
  },
  {
    name: "read_tool_output",
    label: "Read Tool Output",
    description: "Read a bounded excerpt from a canonical Omi tool-output artifact.",
    promptSnippet: "read_tool_output - Read a bounded excerpt from a saved Omi tool result",
    promptGuidelines: [
      "Use an artifactId returned by a toolResultEnvelope fullOutputRef or inspect_agent_artifacts.",
      "The response is bounded; use search_tool_output for targeted retrieval.",
    ],
    capabilityDoc: controlDoc(
      "Read Tool Output",
      "Read a bounded excerpt from a canonical Omi tool-output artifact.",
      ["Requires a canonical artifact id and keeps provider payloads bounded."],
    ),
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...artifactManagePolicy,
    runtimePreconditions: ["Artifact must be a local canonical tool_output owned by the active user."],
    timeoutClass: "normal",
    properties: {
      artifactId: { type: "string", description: "Canonical tool-output artifact_id." },
      ownerId: { type: "string", description: "Owner guard. Defaults to the active signed-in owner." },
      maxBytes: { type: "number", description: "Maximum excerpt size in bytes. Default 4096, max 8192." },
    },
    required: ["artifactId"],
  },
  {
    name: "search_tool_output",
    label: "Search Tool Output",
    description: "Search a canonical Omi tool-output artifact without sending the complete artifact to a provider.",
    promptSnippet: "search_tool_output - Search a saved Omi tool result",
    promptGuidelines: ["Use after a truncated toolResultEnvelope to find the relevant local output."],
    capabilityDoc: controlDoc(
      "Search Tool Output",
      "Search a canonical Omi tool-output artifact without returning the complete artifact.",
      ["Requires a canonical artifact id and returns bounded matching lines."],
    ),
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...artifactManagePolicy,
    runtimePreconditions: ["Artifact must be a local canonical tool_output owned by the active user."],
    timeoutClass: "normal",
    properties: {
      artifactId: { type: "string", description: "Canonical tool-output artifact_id." },
      ownerId: { type: "string", description: "Owner guard. Defaults to the active signed-in owner." },
      query: { type: "string", description: "Text to find in the saved output." },
      maxMatches: { type: "number", description: "Maximum matching lines. Default 5, max 20." },
    },
    required: ["artifactId", "query"],
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
    capabilityDoc: controlDoc(
      "Update Agent Artifact Lifecycle",
      "Update metadata-only lifecycle state for one canonical Omi agent artifact.",
      [
        "Use to mark artifact metadata as retained, dismissed, or opened after a user-visible artifact decision.",
        "Pass sessionId, runId, or attemptId when available as a scope guard.",
        "This never reads artifact contents and has no OS side effects.",
      ],
    ),
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

Creates a new run in that session through the runtime kernel.`,
    promptSnippet: "send_agent_message - Continue an Omi-managed agent session",
    promptGuidelines: [
      "Use when continuing a multi-turn conversation with an Omi-managed agent by sessionId.",
      "Creates a new run in the existing session.",
    ],
    capabilityDoc: controlDoc(
      "Send Agent Message",
      "Send a follow-up message to an existing canonical Omi agent session.",
      [
        "Use when continuing a multi-turn conversation with an Omi-managed agent by sessionId.",
        "Creates a new run in the existing session.",
      ],
    ),
    latency: "async background",
    surfaces: ["desktopChat"],
    riskTier: "medium",
    privacyTier: "local_private",
    approvalPolicy: "policy_grant",
    bundles: ["desktop.agent_control.manage"],
    allowedSurfaces: ["desktopChat"],
    runtimePreconditions: [
      "Defaults ownerId to the active signed-in owner when omitted.",
      "Requires an existing sessionId from list_agent_sessions; cannot create a new session.",
      "Rejects synchronous nested runs when the selected adapter is already executing for the session or has no capacity.",
    ],
    timeoutClass: "long",
    properties: {
      sessionId: { type: "string", description: "Canonical Omi session_id to continue." },
      originSurfaceKind: { type: "string", enum: ["main_chat", "floating_bar", "realtime", "task_chat", "agent_control"], description: "Surface that originated the continuation request. Persisted caller session authority overrides this routing fact." },
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
    required: ["sessionId", "originSurfaceKind", "prompt"],
  },
  {
    name: "spawn_background_agent",
    label: "Spawn Background Agent",
    description: `Internal Swift coordinator entrypoint for creating canonical floating-bar runs.

Not exposed to agent-facing surfaces.`,
    promptSnippet: "spawn_background_agent - Internal coordinator spawn",
    promptGuidelines: ["Swift coordinator entrypoint only."],
    capabilityDoc: controlDoc(
      "Spawn Background Agent",
      "Internal Swift coordinator entrypoint for creating canonical floating-bar runs.",
      ["Swift coordinator entrypoint only; not advertised to agent-facing surfaces."],
    ),
    latency: "async background",
    surfaces: [],
    ...agentControlManagePolicy,
    allowedSurfaces: [],
    runtimePreconditions: [
      "Defaults ownerId to the active signed-in owner when omitted.",
      "Creates a canonical floating_bar session/run by default.",
    ],
    timeoutClass: "long",
    properties: {
      prompt: { type: "string", description: "Self-contained background-agent task prompt." },
      originSurfaceKind: { type: "string", enum: ["main_chat", "floating_bar", "realtime", "task_chat", "agent_control"], description: "Surface that originated the spawn request. Persisted caller session authority overrides this routing fact." },
      title: { type: "string", description: "Optional visible session title." },
      surfaceKind: { type: "string", description: "Optional session surface kind. Default floating_bar." },
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
    required: ["prompt", "originSurfaceKind"],
  },
  {
    name: "spawn_agent",
    label: "Spawn Agent",
    description: `Start canonical Omi background work. Visible runs project into floating-bar pills; invisible runs stay kernel-only child work.

Pass parentRunId to link the new run to a parent.`,
    promptSnippet: "spawn_agent - Start canonical Omi background work",
    promptGuidelines: [
      "Calling spawn_agent is the only way to start a visible floating-bar background agent; saying you will start one does not start it.",
      "Use visible=false for parent-linked background work that should not appear as a pill.",
      "Pass provider='openclaw', provider='hermes', or provider='codex' only when the current user explicitly names that provider; otherwise omit provider so Omi starts its regular managed agent.",
      "Inspect progress with list_agent_sessions or get_agent_run.",
    ],
    capabilityDoc: controlDoc(
      "Spawn Agent",
      "Start canonical Omi background work and optionally project it into floating-bar pills.",
      ["Creates a canonical kernel session/run; visible runs project into floating-bar pills."],
    ),
    latency: "async background",
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlManagePolicy,
    runtimePreconditions: [
      "Defaults ownerId to the active signed-in owner when omitted.",
      "With parentRunId, creates a delegated child session; without it, creates a new top-level background session.",
      "Creates a canonical floating_bar session/run when visible=true.",
    ],
    timeoutClass: "long",
    properties: {
      objective: { type: "string", description: "Self-contained background-agent objective." },
      requestedAgentCount: { type: "number", description: "Number of sibling agents requested in this single canonical route decision (default 1, maximum 8)." },
      provider: {
        type: "string",
        enum: ["openclaw", "hermes", "codex"],
        description: "Optional local provider override only when the current user explicitly names it; omit for a regular Omi agent.",
      },
      parentRunId: { type: "string", description: "Optional parent run to link via delegation." },
      visible: { type: "boolean", description: "Whether to project into floating-bar pill UI. Default true." },
      title: { type: "string", description: "Optional visible session title." },
      externalRefId: { type: "string", description: "Optional stable pill id for UI projection." },
      ownerId: { type: "string", description: "Owner id. Defaults to the active signed-in owner." },
      adapterId: { type: "string", description: "Optional adapter override." },
      cwd: { type: "string", description: "Optional working directory." },
      model: { type: "string", description: "Optional model override." },
      requestId: { type: "string", description: "Optional caller-provided request correlation id." },
      clientId: { type: "string", description: "Logical caller id. Defaults to omi-control-tools." },
      metadata: { type: "object", description: "Small structured metadata for this run.", additionalProperties: true },
    },
    required: ["objective"],
  },
  {
    name: "run_agent_and_wait",
    label: "Run Agent And Wait",
    description: `Run a parent-linked child agent synchronously and return its structured result.`,
    promptSnippet: "run_agent_and_wait - Run a linked child agent and wait for the result",
    promptGuidelines: [
      "Use for synchronous structured child results linked to a known parent run.",
    ],
    capabilityDoc: controlDoc(
      "Run Agent And Wait",
      "Run a parent-linked child agent synchronously and return its structured result.",
      ["Use for synchronous structured child results linked to a known parent run."],
    ),
    latency: "async background",
    surfaces: ["desktopChat"],
    ...agentControlManagePolicy,
    runtimePreconditions: [
      "Requires parentRunId.",
      "Rejects synchronous nested runs when the selected adapter is already executing for the child session or has no capacity.",
    ],
    timeoutClass: "long",
    properties: {
      objective: { type: "string", description: "Delegated objective for the child agent." },
      parentRunId: { type: "string", description: "Canonical parent Omi run_id." },
      originSurfaceKind: { type: "string", enum: ["main_chat", "floating_bar", "realtime", "task_chat", "agent_control"], description: "Surface that originated the synchronous delegation request. Persisted caller session authority overrides this routing fact." },
      context: { type: "string", description: "Optional concise context, not a full transcript." },
      ownerId: { type: "string", description: "Optional owner guard for the parent run." },
      adapterId: { type: "string", description: "Optional adapter override." },
      cwd: { type: "string", description: "Optional working directory." },
      model: { type: "string", description: "Optional model override." },
      runMode: { type: "string", enum: ["ask", "act"], description: "Child run mode. Default ask." },
      requestId: { type: "string", description: "Optional caller-provided request correlation id." },
      clientId: { type: "string", description: "Logical caller id. Defaults to omi-control-tools." },
      maxDepth: { type: "number", description: "Maximum delegation depth for this call. Default 3, hard max 5." },
      maxBudgetUsd: { type: "number", description: "Per-delegation budget guard. Default 5, hard max 10." },
      metadata: { type: "object", description: "Small structured metadata for the child run.", additionalProperties: true },
    },
    required: ["objective", "parentRunId", "originSurfaceKind"],
  },
  {
    name: "set_desktop_attention_override",
    label: "Set Desktop Attention Override",
    description: `Dismiss or hide a kernel-derived attention subject such as a floating-bar run.

Pill dismissal writes here; it never deletes canonical run state.`,
    promptSnippet: "set_desktop_attention_override - Dismiss or hide a derived attention subject",
    promptGuidelines: [
      "Use dismissed=true to hide a floating-bar pill without deleting its canonical run.",
      "Use subjectKind=run and subjectId=<runId> for pill dismissal.",
    ],
    capabilityDoc: controlDoc(
      "Set Desktop Attention Override",
      "Dismiss or hide a kernel-derived attention subject such as a floating-bar run.",
      ["Use dismissed=true to hide floating-bar pills without deleting canonical run state."],
    ),
    latency: "fast local",
    surfaces: ["desktopChat", "realtimeHub"],
    ...agentControlManagePolicy,
    runtimePreconditions: ["Defaults ownerId to the active signed-in owner when omitted."],
    timeoutClass: "normal",
    properties: {
      ownerId: { type: "string", description: "Owner id. Defaults to the active signed-in owner." },
      subjectKind: { type: "string", description: "Attention subject kind, e.g. run or session." },
      subjectId: { type: "string", description: "Attention subject id." },
      dismissed: { type: "boolean", description: "Whether the subject is dismissed. Default true." },
      hiddenUntilMs: { type: "number", description: "Optional epoch-ms hide-until timestamp." },
      reason: { type: "string", description: "Optional short reason." },
    },
    required: ["subjectKind", "subjectId"],
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
