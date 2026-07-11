import {
  agentControlCapabilityManifest,
  agentControlInputSchema,
  type AgentControlManifestTool,
} from "./control-tool-manifest.js";

export type OmiToolAdapterId = "pi-mono" | "omi-tools-stdio" | "local-agent-api";
export type OmiToolCondition =
  | "always"
  | "onboardingOnly"
  | "nonOnboarding"
  | "coordinatorOnly"
  | "screenContext"
  | "screenContextOrOnboarding";
export type OmiToolExecutorKind = "swiftTool" | "runtimeControl" | "nodeTool" | "localApiOnly";
export type OmiToolTimeoutClass = "normal" | "long";
export type OmiToolSurface = "desktop_chat" | "realtime_voice" | "onboarding" | "task_chat";

export interface OmiToolCapabilityDoc {
  title: string;
  summary: string;
  bullets: string[];
}

export interface OmiToolAliasCapabilityDoc extends OmiToolCapabilityDoc {
  surfaces?: OmiToolSurface[];
}

export interface OmiToolVoiceConfig {
  realtimeDescription?: string;
  schemaOverride?: OmiToolInputSchema;
  speakGuidance?: string;
  realtimeExpose?: boolean;
}

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

export type OmiMcpToolInputSchema = OmiToolInputSchema;

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
  surfaces: OmiToolSurface[];
  capabilityDoc: OmiToolCapabilityDoc;
  aliasCapabilityDocs?: Record<string, OmiToolAliasCapabilityDoc>;
  voice?: OmiToolVoiceConfig;
  intendedForAgents: boolean;
  runtimePreconditions: string[];
  adapters: Partial<Record<OmiToolAdapterId, OmiToolAdapterAvailability>>;
}

type OmiToolManifestEntryDraft = Omit<
  OmiToolManifestEntry,
  "surfaces" | "capabilityDoc" | "aliasCapabilityDocs" | "voice"
> &
  Partial<Pick<OmiToolManifestEntry, "surfaces" | "capabilityDoc" | "aliasCapabilityDocs" | "voice">>;

interface OmiToolSurfacePatch {
  surfaces: OmiToolSurface[];
  capabilityDoc: OmiToolCapabilityDoc;
  aliasCapabilityDocs?: Record<string, OmiToolAliasCapabilityDoc>;
  voice?: OmiToolVoiceConfig;
  executor?: OmiToolManifestEntry["executor"];
}

export interface OmiToolProjectionContext {
  onboarding?: boolean;
  screenContext?: boolean;
  executionRole?: "coordinator" | "leaf";
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

function piLocalApiAndScreenContextStdio(): Partial<Record<OmiToolAdapterId, OmiToolAdapterAvailability>> {
  return {
    "pi-mono": { advertised: true },
    "omi-tools-stdio": { advertised: true, condition: "screenContext" },
    "local-agent-api": { advertised: true },
  };
}

function piAndScreenContextOrOnboardingStdio(): Partial<Record<OmiToolAdapterId, OmiToolAdapterAvailability>> {
  return {
    "pi-mono": { advertised: true },
    "omi-tools-stdio": { advertised: true, condition: "screenContextOrOnboarding" },
  };
}

function trustedDirectControlOnly(): Partial<Record<OmiToolAdapterId, OmiToolAdapterAvailability>> {
  return {};
}

function doc(title: string, summary: string, bullets: string[]): OmiToolCapabilityDoc {
  return { title, summary, bullets };
}

function mapControlSurfaces(surfaces: AgentControlManifestTool["surfaces"]): OmiToolSurface[] {
  return surfaces.map((surface) => (surface === "desktopChat" ? "desktop_chat" : "realtime_voice"));
}

function withSurfacePatch(entry: OmiToolManifestEntryDraft, patch: OmiToolSurfacePatch): OmiToolManifestEntry {
  const executor = patch.executor ?? entry.executor;
  if (executor.kind === "swiftTool" && !executor.executorName) {
    executor.executorName = "chatToolExecutor";
  }
  return {
    ...entry,
    ...patch,
    executor,
  };
}

function finalizeManifestEntries(drafts: OmiToolManifestEntryDraft[], patches: Record<string, OmiToolSurfacePatch>): OmiToolManifestEntry[] {
  return drafts.map((entry) => {
    const patch = patches[entry.name];
    if (!patch) {
      throw new Error(`Missing surface patch for tool ${entry.name}`);
    }
    return withSurfacePatch(entry, patch);
  });
}

const swiftToolSurfacePatches: Record<string, OmiToolSurfacePatch> = {
  execute_sql: {
    surfaces: ["desktop_chat"],
    capabilityDoc: doc(
      "Execute SQL",
      "Run SQL on the local omi.db database for structured local data.",
      [
        "Supports SELECT, INSERT, UPDATE, DELETE.",
        "Use for personal facts, app usage stats, time queries, task lookups, conversations, memories, aggregations, and anything structured.",
        "Supports FTS5 MATCH queries for keyword search; see the schema footer for FTS tables and patterns.",
        "SELECT queries auto-limit to 200 rows. UPDATE/DELETE require WHERE. DROP/ALTER/CREATE are blocked.",
        "Prefer semantic_search for fuzzy screen-history questions and backend task tools for creating/updating tasks.",
      ],
    ),
  },
  semantic_search: {
    surfaces: ["desktop_chat"],
    capabilityDoc: doc(
      "Semantic Search",
      "Vector similarity search on the user's screen history.",
      [
        "Use for fuzzy/conceptual questions about what the user saw, read, or worked on where exact SQL keywords will not work.",
        "Examples: \"reading about machine learning\", \"working on design mockups\".",
        "Parameters: query (required), days (default 7), app_filter (optional).",
      ],
    ),
    aliasCapabilityDocs: {
      search_screen_history: {
        ...doc(
          "Search Screen History",
          "Search the user's on-screen history by meaning.",
          ["Use for what the user saw, read, or worked on. Speak a short summary of the result."],
        ),
        surfaces: ["realtime_voice"],
      },
    },
    voice: {
      realtimeDescription:
        "Search the user's on-screen history — what they saw, read, or worked on — by meaning. Use for 'when was I looking at X', 'find where I read about Y', 'what was I doing in app Z'. Returns matching moments with the app and context. Fast synchronous read. Speak the result.",
    },
  },
  get_daily_recap: {
    surfaces: ["desktop_chat", "realtime_voice"],
    capabilityDoc: doc(
      "Daily Recap",
      "Pre-formatted activity recap: apps, conversations, tasks, focus, memories, and observations.",
      [
        "Use for what the user did today/yesterday/this week; it is faster than composing many SQL queries.",
        "Parameters: days_ago (0=today, 1=yesterday, 7=past week; default 1).",
      ],
    ),
    voice: {
      realtimeDescription:
        "Get a recap of what the user actually DID on their Mac — apps used (with minutes), conversations, tasks, focus sessions, and screen activity — for a day. First choice for 'what did I do yesterday', 'what did I do today', 'which apps did I use the most', 'how did I spend my time': one fast synchronous read, where searching conversations or spawning an agent would be slower and less complete. Speak a short summary of what it returns.",
    },
  },
  fill_cloud_connector_form: {
    surfaces: ["desktop_chat"],
    capabilityDoc: doc(
      "Fill Cloud Connector Form",
      "Fill the visible ChatGPT or Claude custom MCP connector form using Omi's native macOS Accessibility automation.",
      [
        "Call this first for ChatGPT or Claude cloud MCP connector setup when the connector form is visible.",
        "Do not install browser extensions before trying this tool.",
      ],
    ),
  },
  search_tasks: {
    surfaces: ["desktop_chat"],
    capabilityDoc: doc(
      "Search Tasks",
      "Vector similarity search on tasks (action_items + staged_tasks).",
      [
        "Use for finding tasks by meaning, not exact keywords, e.g. \"find tasks about shopping\".",
        "Examples: \"tasks about shopping\", \"anything related to the presentation\".",
        "Parameters: query (required), include_completed (default false).",
        "More reliable than hand-writing MATCH queries for task search.",
      ],
    ),
  },
  get_tasks: {
    surfaces: ["realtime_voice"],
    capabilityDoc: doc(
      "Get Tasks",
      "Read the user's overdue and due-today tasks locally.",
      [
        "Use for plain voice questions like what are my tasks, what's due today, or what's on my list.",
        "Prefer get_action_items for completed tasks, date ranges, or the full list.",
      ],
    ),
    executor: { kind: "swiftTool", executorName: "realtimeHub" },
    voice: {
      realtimeDescription:
        "Read the user's tasks (overdue + due today) locally and get them back as text to speak. Fast synchronous read — use this for 'what are my tasks', 'what's due today', 'what's on my list'. Reading tasks is always a direct call, never background work.",
    },
  },
  complete_task: {
    surfaces: ["desktop_chat"],
    capabilityDoc: doc(
      "Complete Task",
      "Toggle a task's completion status by backendId.",
      ["Use after finding the task with execute_sql or search_tasks."],
    ),
  },
  delete_task: {
    surfaces: ["desktop_chat"],
    capabilityDoc: doc(
      "Delete Task",
      "Delete a task permanently by backendId.",
      ["Use after finding the task with execute_sql or search_tasks."],
    ),
  },
  load_skill: {
    surfaces: ["desktop_chat"],
    capabilityDoc: doc("Load Skill", "Load the full instructions for a named skill listed in available_skills.", [
      "Use the exact skill name from available_skills.",
    ]),
  },
  save_knowledge_graph: {
    surfaces: ["desktop_chat"],
    capabilityDoc: doc(
      "Save Knowledge Graph",
      "Save a knowledge graph of entities and relationships extracted from the user's data.",
      [
        "Parameters: nodes (array of {id, label, node_type, aliases}), edges (array of {source_id, target_id, label}).",
        "node_type must be one of: person, organization, place, thing, concept.",
        "Use when exploring the user's files during onboarding to build their knowledge graph.",
        "Deduplication is handled automatically; provide all entities you find.",
      ],
    ),
  },
  get_conversations: {
    surfaces: ["desktop_chat", "realtime_voice"],
    capabilityDoc: doc(
      "Get Conversations",
      "Retrieve conversations by recency or date range.",
      [
        "Use for latest/recent conversations and time-based conversation retrieval.",
        "For voice, this returns summaries only and should be spoken briefly.",
      ],
    ),
    voice: {
      realtimeDescription:
        "List the user's MOST RECENT conversations, newest first (titles + summaries, no full transcripts). Use this — NOT search_conversations — for 'what was my most recent / latest / last conversation', 'what did we just talk about', or 'my recent conversations'. search_conversations is semantic and does NOT order by time, so it's wrong for 'recent'. Fast synchronous read. Speak the result.",
    },
  },
  search_conversations: {
    surfaces: ["desktop_chat", "realtime_voice"],
    capabilityDoc: doc(
      "Search Conversations",
      "Semantic search across the user's past conversations.",
      ["Use for specific topics, decisions, or events discussed in conversations."],
    ),
    voice: {
      realtimeDescription:
        "Search the user's past conversations for what they discussed ('what did I say about X', 'what did we decide', 'summarize my last meeting'). Returns titles + summaries only (no full transcripts). Fast synchronous read. Speak the result.",
    },
  },
  get_memories: {
    surfaces: ["desktop_chat", "realtime_voice"],
    capabilityDoc: doc(
      "Get Memories",
      "Retrieve stored facts, preferences, habits, people, and background about the user.",
      ["Use for broad 'what do you know about me' questions or personal facts."],
    ),
    voice: {
      realtimeDescription:
        "Read what Omi knows about the user — their memories and facts (preferences, background, people, habits). Fast synchronous read with NO query. Use this for 'who am I', 'what do you know about me', 'what are my preferences'. Speak what it returns.",
    },
  },
  search_memories: {
    surfaces: ["desktop_chat", "realtime_voice"],
    capabilityDoc: doc(
      "Search Memories",
      "Semantic search across user memories.",
      ["Use for a specific personal fact that is not already in the visible user context."],
    ),
    voice: {
      realtimeDescription:
        "Search the user's memories / facts for a SPECIFIC thing ('what's my dog's name', 'where do I work', 'what's my partner's name'). Fast synchronous read. Speak the result.",
    },
  },
  get_action_items: {
    surfaces: ["desktop_chat", "realtime_voice"],
    capabilityDoc: doc(
      "Get Action Items",
      "Retrieve the user's tasks with optional completion and due-date filters.",
      [
        "Use for completed tasks, date ranges, or the full task list.",
        "For voice, prefer get_tasks for plain overdue/due-today questions.",
      ],
    ),
    voice: {
      realtimeDescription:
        "Read the user's tasks / to-dos from the backend, with optional filters. Use for COMPLETED tasks ('what did I finish'), a DATE RANGE ('what's due next week'), or the FULL list ('all my tasks') — for plain 'what's due today / overdue', prefer get_tasks. Fast synchronous read. Speak a short summary of what it returns.",
    },
  },
  create_action_item: {
    surfaces: ["desktop_chat", "realtime_voice"],
    capabilityDoc: doc(
      "Create Action Item",
      "Create a new task, to-do, or reminder.",
      [
        "Use when the user explicitly asks to add something to their list.",
        "Pass a concise description and due_at only when the user gave a time.",
      ],
    ),
    voice: {
      realtimeDescription:
        "Create a new task / to-do / reminder for the user ('remind me to…', 'add … to my list', 'I need to…'). Fast synchronous write. Confirm out loud after it returns.",
    },
  },
  update_action_item: {
    surfaces: ["desktop_chat", "realtime_voice"],
    capabilityDoc: doc(
      "Update Action Item",
      "Update an existing task's status, description, or due date.",
      ["Find the task first, then update the matching id. Do not guess task ids."],
    ),
    voice: {
      realtimeDescription:
        "Update an existing task: mark it done, edit its text, or reschedule it. You MUST first call get_tasks to get the matching task's id, then pass that id here. Fast synchronous write.",
      schemaOverride: schema(
        {
          id: { type: "string", description: "The task id from get_tasks." },
          completed: { type: "boolean", description: "Set true to mark the task done." },
          description: { type: "string", description: "New task text, if changing it." },
          due_at: { type: "string", description: "New ISO-8601 due date/time, if rescheduling." },
        },
        ["id"],
      ),
    },
  },
  create_calendar_event: {
    surfaces: ["realtime_voice"],
    capabilityDoc: doc(
      "Create Calendar Event",
      "Create a new Google Calendar event.",
      [
        "Use when the user asks to add, create, schedule, or put a specific event on their calendar.",
        "Pass title, start_time, and end_time as ISO-8601 strings with timezone; include location, description, and attendees when provided.",
        "Use spawn_agent for multi-step calendar work such as finding availability or coordinating with people.",
      ],
    ),
    executor: { kind: "swiftTool" },
    voice: {
      realtimeDescription:
        "Create a Google Calendar event for the user. Use for simple calendar requests like 'put this on my calendar', 'schedule lunch tomorrow', or 'create an event'. Requires start_time and end_time as ISO-8601 strings with timezone. Use spawn_agent instead for multi-step scheduling, finding availability, rescheduling, deleting, or coordinating with people.",
      schemaOverride: schema(
        {
          title: { type: "string", description: "Event title." },
          start_time: {
            type: "string",
            description: "Event start time in ISO-8601 with timezone, e.g. 2026-06-28T14:00:00-04:00.",
          },
          end_time: {
            type: "string",
            description: "Event end time in ISO-8601 with timezone, e.g. 2026-06-28T15:00:00-04:00.",
          },
          description: { type: "string", description: "Optional event description." },
          location: { type: "string", description: "Optional event location." },
          attendees: {
            type: "string",
            description: "Optional comma-separated attendee names or email addresses.",
          },
        },
        ["title", "start_time", "end_time"],
      ),
    },
  },
  capture_screen: {
    surfaces: ["desktop_chat"],
    capabilityDoc: doc(
      "Capture Screen",
      "Capture raw screenshot pixels after screen summary context is not enough.",
      [
        "For screen-awareness questions, call get_work_context first.",
        "Use capture_screen only when raw pixels are necessary; it requires explicit approval before image bytes are shared.",
        "After capture_screen returns a file path, use Read to view the image.",
      ],
    ),
  },
  check_permission_status: {
    surfaces: ["desktop_chat", "realtime_voice", "onboarding"],
    capabilityDoc: doc("Check Permission Status", "Check whether a required macOS permission has been granted.", [
      "Use before requesting a permission or after request_permission returns pending.",
      "Omit type to check all supported permissions.",
    ]),
    voice: {
      realtimeDescription:
        "Check whether Omi has the requested macOS permission. This is a fast local action; use it directly when the user asks to check permissions, never by spawning an agent.",
    },
  },
  request_permission: {
    surfaces: ["desktop_chat", "realtime_voice", "onboarding"],
    capabilityDoc: doc("Request Permission", "Open or guide the user through granting a required macOS permission.", [
      "Use when a tool reports permission_required or the user asks Omi to grant/check a permission.",
      "Use strict permission types only.",
    ]),
    voice: {
      realtimeDescription:
        "Request Omi's macOS permission directly by opening the native prompt or the relevant System Settings pane. Use for Screen Recording, microphone, notifications, Accessibility, Automation, or Full Disk Access. Never use spawn_agent for a permission request.",
    },
  },
  scan_files: {
    surfaces: ["onboarding"],
    capabilityDoc: doc("Scan Files", "Scan selected files/folders during onboarding to build local context.", [
      "Onboarding-only.",
    ]),
  },
  set_user_preferences: {
    surfaces: ["onboarding"],
    capabilityDoc: doc("Set User Preferences", "Persist onboarding preferences such as name and language.", [
      "Onboarding-only.",
    ]),
  },
  ask_followup: {
    surfaces: ["onboarding"],
    capabilityDoc: doc("Ask Followup", "Ask the user a follow-up onboarding question with optional quick replies.", [
      "Onboarding-only.",
    ]),
  },
  complete_onboarding: {
    surfaces: ["onboarding"],
    capabilityDoc: doc("Complete Onboarding", "Complete onboarding after required goals and context are collected.", [
      "Onboarding-only.",
    ]),
  },
  get_email_insights: {
    surfaces: ["onboarding"],
    capabilityDoc: doc(
      "Get Email Insights",
      "Read precomputed email/calendar onboarding insights.",
      ["Onboarding-only; requires background insights to be loaded."],
    ),
  },
  get_local_status: {
    surfaces: ["desktop_chat"],
    capabilityDoc: doc(
      "Get Local Status",
      "Report whether local Omi Desktop context is available.",
      ["Local API only."],
    ),
  },
  get_screenshot: {
    surfaces: ["desktop_chat"],
    capabilityDoc: doc("Get Screenshot", "Fetch a local Rewind screenshot image by screenshot_id.", ["Local API only."]),
  },
  get_work_context: {
    surfaces: ["desktop_chat"],
    capabilityDoc: doc(
      "Get Work Context",
      "Get the user's current screen plus a compressed timeline of recent on-screen activity.",
      [
        "Call this first for \"what is on my screen\", \"do you see my screen\", and current-work questions.",
        "Returns availability, a screenshot_id for follow-up, OCR preview, and recent timeline without raw image bytes.",
        "If raw pixels are needed after this, request get_screenshot/capture_screen approval.",
      ],
    ),
  },
  ask_higher_model: {
    surfaces: ["realtime_voice"],
    capabilityDoc: doc(
      "Ask Higher Model",
      "Get a second opinion from the larger model when the user pushes back or current facts are needed.",
      ["Use sparingly; answer simple or creative requests yourself."],
    ),
    executor: { kind: "swiftTool", executorName: "realtimeHub" },
    voice: {
      realtimeDescription:
        "Get a second opinion from a smarter model and receive text to speak. Use it when the user is dissatisfied with your previous answer (pushes back, rephrases, says you're wrong, or asks for a better/deeper answer), or when you genuinely need precise up-to-date facts you don't know. Answer general, creative, and long-form requests yourself.",
      schemaOverride: schema(
        {
          query: { type: "string", description: "The full question to escalate." },
          context: {
            type: "string",
            description:
              "Relevant context you already have that helps answer well — facts you fetched, what the user is referring to, or the previous answer they pushed back on. Include only what's relevant; omit if there's nothing useful.",
          },
        },
        ["query"],
      ),
    },
  },
  screenshot: {
    surfaces: ["realtime_voice"],
    capabilityDoc: doc("Screenshot", "Capture the user's current screen.", [
      "Use when the user asks about what is on screen.",
    ]),
    executor: { kind: "swiftTool", executorName: "realtimeHub" },
    voice: {
      realtimeDescription: "Capture the user's current screen so you can see what they're looking at.",
    },
  },
  point_click: {
    surfaces: ["realtime_voice"],
    capabilityDoc: doc("Point Click", "Click at on-screen pixel coordinates.", [
      "Use only when the user clearly asks you to click something.",
    ]),
    executor: { kind: "swiftTool", executorName: "realtimeHub" },
    voice: {
      realtimeDescription: "Click the mouse at on-screen pixel coordinates.",
      schemaOverride: schema(
        {
          x: { type: "number", description: "X pixel coordinate." },
          y: { type: "number", description: "Y pixel coordinate." },
        },
        ["x", "y"],
      ),
    },
  },
};

const swiftToolManifestDrafts: OmiToolManifestEntryDraft[] = [
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
      "Capture raw screenshot pixels only when get_work_context is insufficient. Returns the file path to the saved JPEG image after approval. Use the Read tool to view the image after capturing.",
    promptSnippet: "capture_screen - Take a screenshot of the user's current screen",
    promptGuidelines: [
      "Call get_work_context first when the user asks about what's on their screen or what they're looking at.",
      "Use capture_screen only when raw pixels are necessary; it requires explicit approval before image bytes are shared.",
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
    adapters: { "pi-mono": { advertised: true }, "omi-tools-stdio": { advertised: true, condition: "screenContext" } },
  },
  {
    name: "check_permission_status",
    label: "Check Permission Status",
    description: "Check whether a required macOS permission has been granted. Use before requesting access, or after a permission request.",
    promptSnippet: "check_permission_status - Check macOS permission status",
    latency: "fast local",
    inputSchema: schema({
      type: {
        type: "string",
        enum: ["screen_recording", "microphone", "notifications", "accessibility", "automation", "full_disk_access"],
        description: "Optional permission type. Omit to return all supported permissions.",
      },
    }),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires local desktop app."],
    adapters: piAndScreenContextOrOnboardingStdio(),
  },
  {
    name: "request_permission",
    label: "Request Permission",
    description:
      "Request a specific macOS permission from the user by opening the appropriate system prompt or Settings pane. Use when a tool reports permission_required or when the user asks Omi to get a permission.",
    promptSnippet: "request_permission - Request a macOS permission",
    promptGuidelines: [
      "For screen-related requests, if Screen Recording is missing, tell the user Omi cannot see the current screen yet and call request_permission with type=screen_recording.",
      "Use strict permission types only. Do not invent permission names.",
      "After requesting, explain any returned requires_restart or pending status.",
    ],
    latency: "fast local",
    inputSchema: schema(
      {
        type: {
          type: "string",
          enum: ["screen_recording", "microphone", "notifications", "accessibility", "automation", "full_disk_access"],
          description:
            "Permission type: screen_recording, microphone, notifications, accessibility, automation, or full_disk_access",
        },
      },
      ["type"],
    ),
    annotations: localWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires local desktop app; some macOS permissions require the user to toggle Settings manually."],
    adapters: piAndScreenContextOrOnboardingStdio(),
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
    name: "get_tasks",
    label: "Get Tasks",
    description: "Read the user's overdue and due-today tasks locally for voice responses.",
    promptSnippet: "get_tasks - Read overdue and due-today tasks locally",
    latency: "fast local",
    inputSchema: schema({}),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool", executorName: "realtimeHub" },
    intendedForAgents: true,
    runtimePreconditions: ["Realtime voice only; requires local TasksStore."],
    adapters: {},
  },
  {
    name: "create_calendar_event",
    label: "Create Calendar Event",
    description: "Create a Google Calendar event through the backend calendar tool.",
    promptSnippet: "create_calendar_event - Create a Google Calendar event",
    latency: "fast network",
    inputSchema: schema(
      {
        title: { type: "string", description: "Event title." },
        start_time: { type: "string", description: "Event start time in ISO-8601 with timezone." },
        end_time: { type: "string", description: "Event end time in ISO-8601 with timezone." },
        description: { type: "string", description: "Optional event description." },
        location: { type: "string", description: "Optional event location." },
        attendees: { type: "string", description: "Optional comma-separated attendee names or email addresses." },
      },
      ["title", "start_time", "end_time"],
    ),
    annotations: localWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires authenticated backend calendar access."],
    adapters: {},
  },
  {
    name: "ask_higher_model",
    label: "Ask Higher Model",
    description: "Escalate a hard question to the larger model and speak its answer.",
    promptSnippet: "ask_higher_model - Escalate to a higher model for a second opinion",
    latency: "fast network",
    inputSchema: schema(
      {
        query: { type: "string", description: "The full question to escalate." },
        context: { type: "string", description: "Optional relevant context for the escalation." },
      },
      ["query"],
    ),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool", executorName: "realtimeHub" },
    intendedForAgents: true,
    runtimePreconditions: ["Realtime voice only."],
    adapters: {},
  },
  {
    name: "screenshot",
    label: "Screenshot",
    description: "Capture the user's current screen for realtime vision.",
    promptSnippet: "screenshot - Capture the user's current screen",
    latency: "fast local",
    inputSchema: schema({}),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool", executorName: "realtimeHub" },
    intendedForAgents: true,
    runtimePreconditions: ["Realtime voice only; requires Screen Recording permission."],
    adapters: {},
  },
  {
    name: "point_click",
    label: "Point Click",
    description: "Click at on-screen pixel coordinates.",
    promptSnippet: "point_click - Click at on-screen coordinates",
    latency: "fast local",
    inputSchema: schema(
      {
        x: { type: "number", description: "X pixel coordinate." },
        y: { type: "number", description: "Y pixel coordinate." },
      },
      ["x", "y"],
    ),
    annotations: localWrite,
    timeoutClass: "normal",
    executor: { kind: "swiftTool", executorName: "realtimeHub" },
    intendedForAgents: true,
    runtimePreconditions: ["Realtime voice only; requires Accessibility permission."],
    adapters: {},
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
      "Get the user's current screen plus a compressed timeline of recent on-screen activity without sharing raw screenshot pixels. Call this first when seeing the user's current work would help.",
    promptSnippet: "get_work_context - Get current screen and recent work context",
    promptGuidelines: [
      "Call get_work_context first for \"what is on my screen\", \"do you see my screen\", and current-work questions.",
      "Use its screen_now and timeline fields to answer directly when possible.",
      "Only request get_screenshot or capture_screen approval if raw image pixels are necessary after get_work_context.",
    ],
    latency: "fast local",
    inputSchema: schema({ minutes: { type: "number", description: "Minutes of recent activity to summarize (default 10, max 120)" } }),
    annotations: readOnlyLocal,
    timeoutClass: "normal",
    executor: { kind: "swiftTool" },
    intendedForAgents: true,
    runtimePreconditions: ["Requires local Rewind database; raw screenshot pixels still require separate approval."],
    adapters: piLocalApiAndScreenContextStdio(),
  },
];

export const swiftToolManifest: OmiToolManifestEntry[] = finalizeManifestEntries(
  swiftToolManifestDrafts,
  swiftToolSurfacePatches,
);

const controlVoicePatches: Partial<Record<AgentControlManifestTool["name"], OmiToolVoiceConfig>> = {
  spawn_agent: {
    realtimeDescription:
      "Start canonical Omi background work. Visible runs appear as floating-bar pills. Use for multi-step work in the user's apps/browser/files that you cannot do directly.",
    schemaOverride: schema(
      {
        objective: { type: "string", description: "Self-contained background-agent objective." },
        provider: { type: "string", enum: ["openclaw", "hermes"], description: "Optional local provider override." },
        parent_run_id: { type: "string", description: "Optional parent run to link via delegation." },
        visible: { type: "boolean", description: "Whether to project into floating-bar pill UI. Default true." },
        title: { type: "string", description: "Optional visible session title." },
        brief: { type: "string", description: "Optional short user-visible summary for the floating pill." },
      },
      ["objective"],
    ),
  },
  list_agent_sessions: {
    realtimeDescription:
      "List canonical Omi-managed agent sessions/runs across chat, PTT/realtime, task chat, floating-bar pills, and migrated surfaces. Use when the user asks what canonical agents or subagents are active, recent, failed, or manageable.",
    schemaOverride: schema(
      {
        status: { type: "string", enum: ["open", "archived", "closed"], description: "Optional session status filter." },
        surfaceKind: {
          type: "string",
          enum: ["main_chat", "task_chat", "realtime", "delegated_agent", "background_agent", "floating_bar", "floating_pill"],
          description: "Optional canonical surface filter.",
        },
        limit: { type: "number", description: "Maximum sessions to return. Default 50." },
      },
      [],
    ),
  },
  get_agent_run: {
    realtimeDescription: "Inspect one canonical Omi-managed agent run. Prefer an agentRef from list_agent_sessions.",
    schemaOverride: schema(
      {
        agentRef: { type: "string", description: "Opaque agent handle from list_agent_sessions." },
        runId: { type: "string", description: "Canonical Omi run id." },
        includeEvents: { type: "boolean", description: "Include ordered kernel events. Default true." },
        eventLimit: { type: "number", description: "Maximum events to return. Default 100." },
      },
      [],
    ),
  },
  cancel_agent_run: {
    realtimeDescription:
      "Request cancellation for one canonical Omi-managed agent run. Use when the user asks to stop or kill a running canonical agent/subagent.",
    schemaOverride: schema(
      {
        agentRef: { type: "string", description: "Opaque agent handle from list_agent_sessions." },
        runId: { type: "string", description: "Canonical Omi run id to cancel." },
      },
      [],
    ),
  },
  inspect_agent_artifacts: {
    realtimeDescription:
      "Inspect metadata and references for canonical Omi-managed agent artifacts. Does not read arbitrary artifact contents.",
    schemaOverride: schema(
      {
        agentRef: { type: "string", description: "Opaque agent handle from list_agent_sessions." },
        artifactRef: { type: "string", description: "Opaque artifact handle from inspect_agent_artifacts." },
        artifactId: { type: "string", description: "Canonical Omi artifact id." },
        sessionId: { type: "string", description: "Canonical Omi session id." },
        runId: { type: "string", description: "Canonical Omi run id." },
        attemptId: { type: "string", description: "Canonical Omi attempt id." },
        role: {
          type: "string",
          enum: ["input", "result", "checkpoint", "tool_output", "log", "other"],
          description: "Optional artifact role filter.",
        },
        limit: { type: "number", description: "Maximum artifacts to return. Default 50." },
      },
      [],
    ),
  },
  update_agent_artifact_lifecycle: {
    realtimeDescription:
      "Update metadata-only lifecycle state for one canonical Omi-managed agent artifact. Does not open, delete, retain, or read files.",
    schemaOverride: schema(
      {
        artifactRef: { type: "string", description: "Opaque artifact handle from inspect_agent_artifacts." },
        artifactId: { type: "string", description: "Canonical Omi artifact id." },
        state: {
          type: "string",
          enum: ["retained", "dismissed", "opened"],
          description: "Target metadata lifecycle state.",
        },
        sessionId: { type: "string", description: "Optional canonical Omi session id scope guard." },
        runId: { type: "string", description: "Optional canonical Omi run id scope guard." },
        attemptId: { type: "string", description: "Optional canonical Omi attempt id scope guard." },
        reason: { type: "string", description: "Optional short reason." },
      },
      ["state"],
    ),
  },
};

function controlEntry(tool: AgentControlManifestTool): OmiToolManifestEntry {
  const coordinatorOnly = new Set([
    "send_agent_message",
    "spawn_background_agent",
    "spawn_agent",
    "run_agent_and_wait",
  ]);
  const adapters =
    tool.name === "resolve_desktop_dispatch" || tool.name === "spawn_background_agent"
      ? trustedDirectControlOnly()
      : piAndStdio(coordinatorOnly.has(tool.name) ? "coordinatorOnly" : "always");
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
      additionalProperties: false,
    } as OmiMcpToolInputSchema,
    annotations: readOnlyLocal,
    timeoutClass: tool.timeoutClass,
    executor: { kind: "runtimeControl" },
    surfaces: tool.name === "spawn_background_agent" ? [] : mapControlSurfaces(tool.surfaces),
    capabilityDoc: tool.capabilityDoc,
    voice: controlVoicePatches[tool.name],
    intendedForAgents: tool.name !== "spawn_background_agent",
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
  if (availability.condition === "coordinatorOnly") return context.executionRole !== "leaf";
  if (availability.condition === "screenContext") return context.screenContext === true;
  if (availability.condition === "screenContextOrOnboarding") return context.screenContext === true || context.onboarding === true;
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
