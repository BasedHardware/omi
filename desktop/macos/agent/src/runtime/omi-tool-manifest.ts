import {
  agentControlCapabilityManifest,
  agentControlInputSchema,
  type AgentControlManifestTool,
} from "./control-tool-manifest.js";

export type OmiToolAdapterId = "pi-mono" | "omi-tools-stdio" | "local-agent-api";
export type OmiToolCondition = "always" | "onboardingOnly" | "nonOnboarding";
export type OmiToolExecutorKind = "swiftTool" | "runtimeControl" | "nodeTool" | "localApiOnly";
export type OmiToolTimeoutClass = "normal" | "long";

export interface OmiToolAnnotations {
  readOnlyHint?: boolean;
  destructiveHint?: boolean;
  idempotentHint?: boolean;
  openWorldHint?: boolean;
}

export interface OmiToolInputSchema {
  type: "object";
  properties: Record<string, unknown>;
  required?: string[];
  additionalProperties?: boolean;
}

export interface OmiMcpToolInputSchema extends OmiToolInputSchema {
  anyOf?: unknown[];
  allOf?: unknown[];
  oneOf?: unknown[];
  if?: unknown;
  then?: unknown;
}

export interface OmiToolAdapterAvailability {
  advertised: boolean;
  condition?: OmiToolCondition;
  adapterName?: string;
  aliases?: string[];
}

export interface OmiToolManifestEntry {
  name: string;
  label: string;
  description: string;
  promptSnippet: string;
  promptGuidelines?: string[];
  latency: "fast local" | "fast network" | "async background";
  inputSchema: OmiToolInputSchema;
  mcpInputSchema?: OmiMcpToolInputSchema;
  annotations: OmiToolAnnotations;
  timeoutClass: OmiToolTimeoutClass;
  executor: {
    kind: OmiToolExecutorKind;
    executorName?: string;
  };
  aliases?: string[];
  intendedForAgents: boolean;
  runtimePreconditions: string[];
  adapters: Partial<Record<OmiToolAdapterId, OmiToolAdapterAvailability>>;
}

export interface OmiToolProjectionContext {
  onboarding?: boolean;
}

export interface OmiToolAvailabilitySnapshot {
  manifestVersion: number;
  adapterId: OmiToolAdapterId;
  context: OmiToolProjectionContext;
  advertisedToolCount: number;
  advertisedToolNames: string[];
  aliases: Record<string, string>;
  disabled: Array<{ name: string; reason: string }>;
}

const readOnlyLocal: OmiToolAnnotations = {
  readOnlyHint: true,
  destructiveHint: false,
  openWorldHint: false,
};

const localWrite: OmiToolAnnotations = {
  readOnlyHint: false,
  destructiveHint: false,
  openWorldHint: false,
};

const openWorldWrite: OmiToolAnnotations = {
  readOnlyHint: false,
  destructiveHint: false,
  openWorldHint: true,
};

const destructiveLocal: OmiToolAnnotations = {
  readOnlyHint: false,
  destructiveHint: true,
  openWorldHint: false,
};

function schema(properties: Record<string, unknown>, required: string[] = []): OmiToolInputSchema {
  return {
    type: "object",
    properties,
    required,
    additionalProperties: false,
  };
}

function piAndStdio(condition: OmiToolCondition = "always"): Partial<Record<OmiToolAdapterId, OmiToolAdapterAvailability>> {
  return {
    "pi-mono": { advertised: condition !== "onboardingOnly", condition: condition === "always" ? undefined : condition },
    "omi-tools-stdio": { advertised: true, condition: condition === "always" ? undefined : condition },
  };
}

function stdioOnly(condition: OmiToolCondition = "always"): Partial<Record<OmiToolAdapterId, OmiToolAdapterAvailability>> {
  return {
    "omi-tools-stdio": { advertised: true, condition: condition === "always" ? undefined : condition },
  };
}

function localApiOnly(): Partial<Record<OmiToolAdapterId, OmiToolAdapterAvailability>> {
  return {
    "local-agent-api": { advertised: true },
  };
}

function trustedDirectControlOnly(): Partial<Record<OmiToolAdapterId, OmiToolAdapterAvailability>> {
  return {};
}

export const swiftToolManifest: OmiToolManifestEntry[] = [
  {
    name: "execute_sql",
    label: "Execute SQL",
    description:
      "Run SQL on the user's local omi.db SQLite database. Use for app usage stats, screen time, activity counts, task lookups, aggregations. Read-only in agent adapters.",
    promptSnippet: "execute_sql - Query the user's local omi.db SQLite database (SELECT only)",
    promptGuidelines: [
      "Use execute_sql for quantitative queries (counts, sums, date ranges, aggregations).",
      "Use semantic_search instead for fuzzy or conceptual queries about screen content.",
    ],
    latency: "fast local",
    inputSchema: schema({ query: { type: "string", description: "SQL query to execute" } }, ["query"]),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["SELECT-only in ask-mode and local-agent API projections."],
    adapters: {
      ...piAndStdio(),
      "local-agent-api": { advertised: true },
    },
  },
  {
    name: "semantic_search",
    label: "Semantic Search",
    description:
      "Vector similarity search on the user's screen history. Use for fuzzy/conceptual queries about what the user saw on their computer.",
    promptSnippet: "semantic_search - Search screen history by meaning",
    promptGuidelines: ["Prefer semantic_search over execute_sql when the user asks about something they 'saw' or worked on."],
    latency: "fast local",
    inputSchema: schema(
      {
        query: { type: "string", description: "Natural language search query" },
        days: { type: "number", description: "Days to search back (default 7)" },
        app_filter: { type: "string", description: "Filter to a specific app" },
      },
      ["query"],
    ),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    aliases: ["search_screen_history"],
    intendedForAgents: true,
    runtimePreconditions: ["Requires local Rewind screen-history data."],
    adapters: {
      ...piAndStdio(),
      "local-agent-api": { advertised: true, adapterName: "search_screen_history", aliases: ["semantic_search"] },
    },
  },
  {
    name: "get_daily_recap",
    label: "Daily Recap",
    description: "Pre-formatted daily activity recap: app usage, conversations, tasks, focus, memories, observations.",
    promptSnippet: "get_daily_recap - Get a daily activity summary",
    latency: "fast local",
    inputSchema: schema({ days_ago: { type: "number", description: "0=today, 1=yesterday, 7=past week" } }),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires local Omi activity data."],
    adapters: {
      ...piAndStdio(),
      "local-agent-api": { advertised: true },
    },
  },
  {
    name: "get_task_agent_status",
    label: "Task Agent Status",
    description:
      "Inspect Omi's local task-chat agents/subagents and floating agent pills. Use when the user asks about your subagents, task agents, running agents, finished agents, errors, or timeouts.",
    promptSnippet: "get_task_agent_status - Inspect Omi task-chat agents and floating agent pills",
    promptGuidelines: [
      "If the user says 'your subagents', interpret that as Omi task-chat agents, not Cursor or external IDE agents.",
      "Call this before claiming there are no subagents or before diagnosing a task-agent timeout.",
    ],
    latency: "fast local",
    inputSchema: schema({}),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires the desktop app task-agent stores."],
    adapters: piAndStdio(),
  },
  {
    name: "fill_cloud_connector_form",
    label: "Fill Cloud Connector Form",
    description:
      "Fill the currently visible ChatGPT or Claude custom MCP connector form using Omi's native macOS Accessibility automation. Use first for one-click cloud connector setup after opening the signed-in browser to the connector page.",
    promptSnippet: "fill_cloud_connector_form - Fill and optionally submit the visible ChatGPT/Claude MCP connector form",
    promptGuidelines: [
      "Call this first for ChatGPT or Claude cloud MCP connector setup when the connector form is visible.",
      "Do not install browser extensions before trying this tool.",
      "If it reports missing Accessibility permission, missing form, or missing required fields, wait for the missing condition or use guarded screenshots before any keyboard automation.",
    ],
    latency: "fast local",
    inputSchema: schema(
      {
        provider: {
          type: "string",
          enum: ["claude", "chatgpt"],
          description: "Cloud platform whose connector form is visible.",
        },
        name: { type: "string", description: "Connector name, usually 'Omi Memory'." },
        server_url: { type: "string", description: "Remote MCP server URL to paste into the connector form." },
        oauth_client_id: {
          type: "string",
          description: "OAuth Client ID. Defaults to Omi's public ChatGPT/Claude connector client.",
        },
        oauth_client_secret: { type: "string", description: "OAuth Client Secret, only for confidential clients." },
        authentication: { type: "string", description: "Authentication mode, usually 'OAuth'." },
        token_auth_method: {
          type: "string",
          description: "OAuth token auth method. Use 'none' for Omi's public ChatGPT connector client.",
        },
        auth_url: { type: "string", description: "OAuth authorization URL when the form asks for it." },
        token_url: { type: "string", description: "OAuth token URL when the form asks for it." },
        submit: {
          type: "boolean",
          description: "Whether to press the visible Add/Connect/Create button after filling required fields.",
        },
      },
      ["provider", "server_url"],
    ),
    annotations: openWorldWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: [
      "Requires a signed-in supported browser on the connector page.",
      "Requires macOS Accessibility permission for Omi and the target browser.",
    ],
    adapters: {
      ...piAndStdio(),
      "local-agent-api": { advertised: true },
    },
  },
  {
    name: "spawn_agent",
    label: "Spawn Agent",
    description:
      "Start canonical Omi background work and show it in the floating-bar pill UI. Use when the user explicitly asks for a visible floating/background agent, or for multi-step work in other apps/browser/files.",
    promptSnippet: "spawn_agent - Start a canonical background agent with pill UI",
    promptGuidelines: [
      "Calling spawn_agent is the only way to start the circular floating-bar subagent; saying you will start one does not start it.",
      "Use delegate_agent instead when the new work must be linked to a known parent run.",
      "If the user asks to use OpenClaw or Hermes, pass provider='openclaw' or provider='hermes' instead of treating that name as a session to inspect.",
      "Return immediately after spawning; the pill keeps working in the background.",
    ],
    latency: "async background",
    inputSchema: schema(
      {
        brief: { type: "string", description: "Clear, self-contained task brief for the background agent." },
        title: { type: "string", description: "Short Title Case label for the agent pill." },
        provider: {
          type: "string",
          enum: ["openclaw", "hermes"],
          description: "Optional local agent provider to run this pill through.",
        },
      },
      ["brief"],
    ),
    annotations: localWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires Swift AgentBridge/floating pill support."],
    adapters: piAndStdio(),
  },
  {
    name: "manage_agent_pills",
    label: "Manage Agent Pills",
    description: "List, dismiss, or clear completed floating agent pills shown below the floating bar.",
    promptSnippet: "manage_agent_pills - List, dismiss, or clear completed floating agent pills",
    promptGuidelines: [
      "Call get_task_agent_status first when dismissing a specific pill so you have its id.",
      "Use clear_completed only when the user asks to clear finished/done agents.",
    ],
    latency: "fast local",
    inputSchema: schema(
      {
        action: { type: "string", enum: ["list", "dismiss", "clear_completed"], description: "Management action." },
        agent_id: { type: "string", description: "Floating agent pill id from get_task_agent_status; required for dismiss." },
      },
      ["action"],
    ),
    annotations: localWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires Swift floating agent pill registry."],
    adapters: piAndStdio(),
  },
  {
    name: "search_tasks",
    label: "Search Tasks",
    description: "Vector similarity search on tasks. Find tasks by meaning or topic.",
    promptSnippet: "search_tasks - Find tasks by meaning",
    latency: "fast local",
    inputSchema: schema(
      {
        query: { type: "string", description: "Natural language task description" },
        include_completed: { type: "boolean", description: "Include completed tasks" },
      },
      ["query"],
    ),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires local task index."],
    adapters: {
      ...piAndStdio(),
      "local-agent-api": { advertised: true },
    },
  },
  {
    name: "complete_task",
    label: "Complete Task",
    description: "Toggle a task's completion status. Syncs to backend.",
    promptSnippet: "complete_task - Mark a task as complete/incomplete",
    latency: "fast local",
    inputSchema: schema({ task_id: { type: "string", description: "backendId from action_items" } }, ["task_id"]),
    annotations: localWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires a backendId found via execute_sql or search_tasks."],
    adapters: {
      ...piAndStdio(),
      "local-agent-api": { advertised: true },
    },
  },
  {
    name: "delete_task",
    label: "Delete Task",
    description: "Delete a task permanently. Syncs to backend.",
    promptSnippet: "delete_task - Delete a task permanently",
    latency: "fast local",
    inputSchema: schema({ task_id: { type: "string", description: "backendId from action_items" } }, ["task_id"]),
    annotations: destructiveLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires a backendId found via execute_sql or search_tasks."],
    adapters: {
      ...piAndStdio(),
      "local-agent-api": { advertised: true },
    },
  },
  {
    name: "load_skill",
    label: "Load Skill",
    description: "Load the full instructions for a named skill listed in available_skills.",
    promptSnippet: "load_skill - Load the full SKILL.md instructions for an available skill",
    latency: "fast local",
    inputSchema: schema({ name: { type: "string", description: "Skill name exactly as listed in available_skills" } }, ["name"]),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "nodeTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires a local SKILL.md under the configured skill roots."],
    adapters: piAndStdio(),
  },
  {
    name: "save_knowledge_graph",
    label: "Save Knowledge Graph",
    description: "Save a knowledge graph of entities and relationships discovered about the user.",
    promptSnippet: "save_knowledge_graph - Save entities and relationships to the user's knowledge graph",
    promptGuidelines: [
      "Use when exploring the user's files during onboarding or knowledge-graph building.",
      "Deduplication is handled automatically; include all meaningful entities and relationships you found.",
    ],
    latency: "fast local",
    inputSchema: schema(
      {
        nodes: {
          type: "array",
          items: {
            type: "object",
            properties: {
              id: { type: "string", description: "Stable node id, referenced by edges." },
              label: { type: "string", description: "Human-readable entity label." },
              node_type: { type: "string", enum: ["person", "organization", "place", "thing", "concept"] },
              aliases: { type: "array", items: { type: "string" } },
            },
            required: ["id", "label", "node_type"],
            additionalProperties: false,
          },
        },
        edges: {
          type: "array",
          items: {
            type: "object",
            properties: {
              source_id: { type: "string" },
              target_id: { type: "string" },
              label: { type: "string" },
            },
            required: ["source_id", "target_id", "label"],
            additionalProperties: false,
          },
        },
      },
      ["nodes", "edges"],
    ),
    annotations: localWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Used by onboarding/knowledge graph flows."],
    adapters: piAndStdio(),
  },
  {
    name: "get_conversations",
    label: "Get Conversations",
    description: "Retrieve user conversations with summaries, action items, metadata. Use for time-based queries or recaps.",
    promptSnippet: "get_conversations - Retrieve conversations by date range",
    latency: "fast network",
    inputSchema: schema({
      start_date: { type: "string", description: "ISO date with timezone" },
      end_date: { type: "string", description: "ISO date with timezone" },
      limit: { type: "number", description: "Default 20" },
      offset: { type: "number" },
      include_transcript: { type: "boolean", description: "Load speaker data" },
    }),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires authenticated backend access."],
    adapters: piAndStdio(),
  },
  {
    name: "search_conversations",
    label: "Search Conversations",
    description: "Semantic search across conversations. Use for specific events or topics.",
    promptSnippet: "search_conversations - Find conversations about a topic",
    latency: "fast network",
    inputSchema: schema(
      {
        query: { type: "string", description: "Event or topic to search for" },
        start_date: { type: "string" },
        end_date: { type: "string" },
        limit: { type: "number", description: "Default 5, max 20" },
        include_transcript: { type: "boolean" },
      },
      ["query"],
    ),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires authenticated backend access."],
    adapters: piAndStdio(),
  },
  {
    name: "get_memories",
    label: "Get Memories",
    description: "Retrieve user memories - facts, preferences, habits. Use for 'what do you know about me?' type questions.",
    promptSnippet: "get_memories - Retrieve stored facts and preferences",
    latency: "fast network",
    inputSchema: schema({
      limit: { type: "number", description: "Default 50" },
      offset: { type: "number" },
      start_date: { type: "string" },
      end_date: { type: "string" },
    }),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires authenticated backend access."],
    adapters: piAndStdio(),
  },
  {
    name: "search_memories",
    label: "Search Memories",
    description: "Semantic search across user memories. Find memories about a topic using AI embeddings.",
    promptSnippet: "search_memories - Find memories about a topic",
    latency: "fast network",
    inputSchema: schema(
      {
        query: { type: "string", description: "Topic to search for" },
        limit: { type: "number", description: "Default 5, max 20" },
      },
      ["query"],
    ),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires authenticated backend access."],
    adapters: piAndStdio(),
  },
  {
    name: "get_action_items",
    label: "Get Action Items",
    description: "Retrieve user tasks from Omi backend. Filter by completion status or due date.",
    promptSnippet: "get_action_items - Retrieve tasks",
    latency: "fast network",
    inputSchema: schema({
      limit: { type: "number" },
      offset: { type: "number" },
      completed: { type: "boolean", description: "true=done, false=pending" },
      start_date: { type: "string" },
      end_date: { type: "string" },
      due_start_date: { type: "string" },
      due_end_date: { type: "string" },
    }),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires authenticated backend access."],
    adapters: piAndStdio(),
  },
  {
    name: "create_action_item",
    label: "Create Action Item",
    description: "Create a new task. Use when user explicitly asks to add a task.",
    promptSnippet: "create_action_item - Create a new task",
    latency: "fast network",
    inputSchema: schema(
      {
        description: { type: "string", description: "Short task description" },
        due_at: { type: "string", description: "Due date ISO" },
        conversation_id: { type: "string" },
      },
      ["description"],
    ),
    annotations: localWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires authenticated backend access."],
    adapters: piAndStdio(),
  },
  {
    name: "update_action_item",
    label: "Update Action Item",
    description: "Update task status, description, or due date.",
    promptSnippet: "update_action_item - Update an existing task",
    latency: "fast network",
    inputSchema: schema(
      {
        action_item_id: { type: "string", description: "Task ID (required)" },
        completed: { type: "boolean" },
        description: { type: "string" },
        due_at: { type: "string" },
      },
      ["action_item_id"],
    ),
    annotations: localWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires authenticated backend access."],
    adapters: piAndStdio(),
  },
  {
    name: "capture_screen",
    label: "Capture Screen",
    description:
      "Capture a screenshot of the user's current screen. Returns the file path to the saved JPEG image. Use the Read tool to view the image after capturing.",
    promptSnippet: "capture_screen - Take a screenshot of the user's current screen",
    promptGuidelines: [
      "Call capture_screen when the user asks about what's on their screen or what they're looking at.",
      "After capture_screen returns a file path, use Read to view the image.",
      "Do NOT use bash screencapture - always use this tool instead.",
    ],
    latency: "fast local",
    inputSchema: schema({}),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires macOS Screen Recording permission."],
    adapters: { "pi-mono": { advertised: true } },
  },
  {
    name: "check_permission_status",
    label: "Check Permission Status",
    description: "Check whether a required macOS permission has been granted.",
    promptSnippet: "check_permission_status - Check macOS permission status",
    latency: "fast local",
    inputSchema: schema({}),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Onboarding-only."],
    adapters: stdioOnly("onboardingOnly"),
  },
  {
    name: "request_permission",
    label: "Request Permission",
    description: "Open or guide the user through granting a required macOS permission.",
    promptSnippet: "request_permission - Request a macOS permission",
    latency: "fast local",
    inputSchema: schema(
      {
        type: {
          type: "string",
          enum: ["screen_recording", "microphone", "accessibility", "automation", "full_disk_access"],
          description:
            "Permission type: screen_recording, microphone, accessibility, automation, or full_disk_access",
        },
      },
      ["type"],
    ),
    annotations: localWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Onboarding-only."],
    adapters: stdioOnly("onboardingOnly"),
  },
  {
    name: "scan_files",
    label: "Scan Files",
    description: "Scan selected files/folders during onboarding to build local context.",
    promptSnippet: "scan_files - Scan files for onboarding context",
    latency: "async background",
    inputSchema: schema({ paths: { type: "array", items: { type: "string" } } }),
    annotations: readOnlyLocal,
    timeoutClass: "long",
    executor: { kind: "swiftTool" },
    aliases: ["start_file_scan", "get_file_scan_results"],
    intendedForAgents: true,
    runtimePreconditions: ["Onboarding-only."],
    adapters: stdioOnly("onboardingOnly"),
  },
  {
    name: "set_user_preferences",
    label: "Set User Preferences",
    description: "Persist onboarding preferences such as name and language.",
    promptSnippet: "set_user_preferences - Save onboarding preferences",
    latency: "fast local",
    inputSchema: schema({
      name: { type: "string" },
      language: { type: "string" },
    }),
    annotations: localWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Onboarding-only."],
    adapters: stdioOnly("onboardingOnly"),
  },
  {
    name: "ask_followup",
    label: "Ask Followup",
    description: "Ask the user a follow-up onboarding question with optional quick replies.",
    promptSnippet: "ask_followup - Ask an onboarding follow-up question",
    latency: "async background",
    inputSchema: schema(
      {
        question: { type: "string", description: "The question to present to the user" },
        options: {
          type: "array",
          items: { type: "string" },
          description: "2-3 quick-reply button labels. For permissions, include 'Grant [Permission]' and 'Skip'.",
        },
      },
      ["question", "options"],
    ),
    annotations: localWrite,
    timeoutClass: "long",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Onboarding-only."],
    adapters: stdioOnly("onboardingOnly"),
  },
  {
    name: "complete_onboarding",
    label: "Complete Onboarding",
    description: "Complete onboarding after required goals and context are collected.",
    promptSnippet: "complete_onboarding - Complete onboarding",
    latency: "fast local",
    inputSchema: schema({}),
    annotations: localWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Onboarding-only."],
    adapters: stdioOnly("onboardingOnly"),
  },
  {
    name: "get_email_insights",
    label: "Get Email Insights",
    description: "Read precomputed email/calendar onboarding insights.",
    promptSnippet: "get_email_insights - Read onboarding email/calendar insights",
    latency: "fast local",
    inputSchema: schema({}),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Onboarding-only; requires background insights to be loaded."],
    adapters: stdioOnly("onboardingOnly"),
  },
  {
    name: "get_local_status",
    label: "Get Local Status",
    description:
      "Report whether local Omi Desktop context is available, including screen-history counts, indexed screenshot counts, and latest capture time.",
    promptSnippet: "get_local_status - Check local desktop context status",
    latency: "fast local",
    inputSchema: schema({}),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "localApiOnly" },
    intendedForAgents: true,
    runtimePreconditions: ["Local API only."],
    adapters: localApiOnly(),
  },
  {
    name: "get_screenshot",
    label: "Get Screenshot",
    description: "Fetch a local Rewind screenshot image by screenshot_id.",
    promptSnippet: "get_screenshot - Fetch a local screenshot image",
    latency: "fast local",
    inputSchema: schema({ screenshot_id: { type: "number", description: "Screenshot ID from search_screen_history or screenshots table" } }, ["screenshot_id"]),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "localApiOnly" },
    intendedForAgents: true,
    runtimePreconditions: ["Local API only."],
    adapters: localApiOnly(),
  },
  {
    name: "get_work_context",
    label: "Get Work Context",
    description:
      "Get the user's current screen plus a compressed timeline of recent on-screen activity. Call this first when seeing the user's current work would help.",
    promptSnippet: "get_work_context - Get current screen and recent work context",
    latency: "fast local",
    inputSchema: schema({ minutes: { type: "number", description: "Minutes of recent activity to summarize (default 10, max 120)" } }),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "localApiOnly" },
    intendedForAgents: true,
    runtimePreconditions: ["Local API only."],
    adapters: localApiOnly(),
  },
] satisfies OmiToolManifestEntry[];

function controlEntry(tool: AgentControlManifestTool): OmiToolManifestEntry {
  const adapters = tool.name === "resolve_desktop_dispatch" ? trustedDirectControlOnly() : piAndStdio();
  return {
    name: tool.name,
    label: tool.label,
    description: tool.description,
    promptSnippet: tool.promptSnippet,
    promptGuidelines: tool.promptGuidelines,
    latency: tool.latency,
    inputSchema: {
      ...agentControlInputSchema(tool),
      additionalProperties: false,
    } as OmiToolInputSchema,
    mcpInputSchema: {
      ...agentControlInputSchema(tool),
      ...tool.mcpInputSchemaOptions,
      additionalProperties: false,
    } as OmiMcpToolInputSchema,
    annotations: readOnlyLocal,
    timeoutClass: tool.timeoutClass,
    executor: { kind: "runtimeControl" },
    intendedForAgents: true,
    runtimePreconditions: tool.runtimePreconditions,
    adapters,
  };
}

export const omiToolManifest: OmiToolManifestEntry[] = [
  ...swiftToolManifest.slice(0, 4),
  ...agentControlCapabilityManifest.map(controlEntry),
  ...swiftToolManifest.slice(4),
] satisfies OmiToolManifestEntry[];

export function isToolAvailableForContext(
  availability: OmiToolAdapterAvailability | undefined,
  context: OmiToolProjectionContext = {},
): boolean {
  if (!availability?.advertised) return false;
  if (availability.condition === "onboardingOnly") return context.onboarding === true;
  if (availability.condition === "nonOnboarding") return context.onboarding !== true;
  return true;
}

export function toolsForAdapter(
  adapterId: OmiToolAdapterId,
  context: OmiToolProjectionContext = {},
): OmiToolManifestEntry[] {
  return omiToolManifest.filter((tool) => isToolAvailableForContext(tool.adapters[adapterId], context));
}

export function toolNamesForAdapter(
  adapterId: OmiToolAdapterId,
  context: OmiToolProjectionContext = {},
): string[] {
  return toolsForAdapter(adapterId, context).map((tool) => tool.adapters[adapterId]?.adapterName ?? tool.name);
}

export function mcpToolDefinitionsForAdapter(
  adapterId: "omi-tools-stdio",
  context: OmiToolProjectionContext = {},
): Array<{ name: string; description: string; inputSchema: OmiMcpToolInputSchema }> {
  return toolsForAdapter(adapterId, context).map((tool) => ({
    name: tool.adapters[adapterId]?.adapterName ?? tool.name,
    description: tool.description,
    inputSchema: tool.mcpInputSchema ?? tool.inputSchema,
  }));
}

export function toolManifestEntry(name: string): OmiToolManifestEntry | undefined {
  return omiToolManifest.find((tool) => tool.name === name || tool.aliases?.includes(name));
}

export function normalizeOmiToolName(
  adapterId: OmiToolAdapterId,
  name: string,
): { canonicalName: string; wasAlias: boolean } {
  const mcpMatch = /^mcp__(?:omi-tools|omi_tools)__(.+)$/.exec(name);
  const dotMatch = /^omi-tools\.(.+)$/.exec(name);
  const unprefixed = mcpMatch?.[1] ?? dotMatch?.[1] ?? name;

  for (const tool of omiToolManifest) {
    const availability = tool.adapters[adapterId];
    const adapterName = availability?.adapterName ?? tool.name;
    const aliases = new Set([...(tool.aliases ?? []), ...(availability?.aliases ?? [])]);
    if (adapterName === unprefixed || tool.name === unprefixed) {
      return { canonicalName: tool.name, wasAlias: unprefixed !== tool.name || name !== unprefixed };
    }
    if (aliases.has(unprefixed)) {
      return { canonicalName: tool.name, wasAlias: true };
    }
  }
  return { canonicalName: unprefixed, wasAlias: name !== unprefixed };
}

export function buildToolAvailabilitySnapshot(
  adapterId: OmiToolAdapterId,
  context: OmiToolProjectionContext = {},
): OmiToolAvailabilitySnapshot {
  const advertised = toolsForAdapter(adapterId, context);
  const aliases: Record<string, string> = {};
  const disabled: Array<{ name: string; reason: string }> = [];

  for (const tool of omiToolManifest) {
    const availability = tool.adapters[adapterId];
    if (isToolAvailableForContext(availability, context)) {
      for (const alias of [...(tool.aliases ?? []), ...(availability?.aliases ?? [])]) {
        aliases[alias] = tool.name;
      }
      aliases[`mcp__omi-tools__${tool.name}`] = tool.name;
      aliases[`mcp__omi_tools__${tool.name}`] = tool.name;
      aliases[`omi-tools.${tool.name}`] = tool.name;
    } else {
      disabled.push({
        name: availability?.adapterName ?? tool.name,
        reason: availability?.condition ?? (availability ? "notAdvertised" : "adapterUnavailable"),
      });
    }
  }

  return {
    manifestVersion: 1,
    adapterId,
    context,
    advertisedToolCount: advertised.length,
    advertisedToolNames: toolNamesForAdapter(adapterId, context),
    aliases,
    disabled,
  };
}
