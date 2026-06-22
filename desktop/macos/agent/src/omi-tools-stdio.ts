/**
 * Stdio-based MCP server for omi tools (execute_sql, semantic_search).
 * This script is spawned as a subprocess by the ACP agent.
 * It reads JSON-RPC requests from stdin and writes responses to stdout.
 *
 * Tool calls are forwarded to the parent agent process via a named pipe
 * (passed as OMI_BRIDGE_PIPE env var), which then forwards them to Swift.
 */

import { createInterface } from "readline";
import { createConnection } from "net";
import { readFileSync } from "fs";
import { join } from "path";
import { homedir } from "os";

// Current query mode
let currentMode: "ask" | "act" = process.env.OMI_QUERY_MODE === "ask" ? "ask" : "act";

// Connection to parent bridge for tool forwarding
const bridgePipePath = process.env.OMI_BRIDGE_PIPE;

// Pending tool calls — resolved when parent sends back results via pipe
const pendingToolCalls = new Map<
  string,
  { resolve: (result: string) => void }
>();

let callIdCounter = 0;

function nextCallId(): string {
  return `omi-${++callIdCounter}-${Date.now()}`;
}

function logErr(msg: string): void {
  process.stderr.write(`[omi-tools-stdio] ${msg}\n`);
}

// --- Communication with parent bridge ---

let pipeConnection: ReturnType<typeof createConnection> | null = null;
let pipeBuffer = "";

function connectToPipe(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (!bridgePipePath) {
      logErr("No OMI_BRIDGE_PIPE set, tool calls will fail");
      resolve();
      return;
    }

    pipeConnection = createConnection(bridgePipePath, () => {
      logErr(`Connected to bridge pipe: ${bridgePipePath}`);
      resolve();
    });

    pipeConnection.on("data", (data: Buffer) => {
      pipeBuffer += data.toString();
      // Process complete lines
      let newlineIdx;
      while ((newlineIdx = pipeBuffer.indexOf("\n")) >= 0) {
        const line = pipeBuffer.slice(0, newlineIdx);
        pipeBuffer = pipeBuffer.slice(newlineIdx + 1);
        if (line.trim()) {
          try {
            const msg = JSON.parse(line) as {
              type: string;
              callId: string;
              result: string;
            };
            if (msg.type === "tool_result" && msg.callId) {
              const pending = pendingToolCalls.get(msg.callId);
              if (pending) {
                pending.resolve(msg.result);
                pendingToolCalls.delete(msg.callId);
              }
            }
          } catch {
            logErr(`Failed to parse pipe message: ${line.slice(0, 200)}`);
          }
        }
      }
    });

    pipeConnection.on("error", (err) => {
      logErr(`Pipe error: ${err.message}`);
      reject(err);
    });
  });
}

async function requestSwiftTool(
  name: string,
  input: Record<string, unknown>
): Promise<string> {
  const callId = nextCallId();

  if (!pipeConnection) {
    return "Error: not connected to bridge";
  }

  return new Promise<string>((resolve) => {
    pendingToolCalls.set(callId, { resolve });
    const msg = JSON.stringify({ type: "tool_use", callId, name, input });
    pipeConnection!.write(msg + "\n");
  });
}

// --- MCP tool definitions ---

const isOnboarding = process.env.OMI_ONBOARDING === "true";

const ONBOARDING_TOOL_NAMES = new Set([
  "check_permission_status",
  "request_permission",
  "scan_files",
  "set_user_preferences",
  "ask_followup",
  "complete_onboarding",
  "save_knowledge_graph",
]);

// Tool order: local tools first (always available), then backend RAG tools (require auth token).
// Within each group, order is stable for prompt cache hits.
const ALL_TOOLS = [
  {
    name: "execute_sql",
    description: `Run SQL on the user's local omi.db SQLite database for structured data queries.

Use when:
- User asks for app usage stats, screen time, or activity counts
- Time-based queries like "how long did I spend on X?"
- Task management: looking up action items, checking completion status
- Aggregations, rankings, or structured filters on local data

Don't use when (if those tools are available):
- User asks about conversation content or transcripts (prefer get_conversations or search_conversations)
- User asks about their preferences or facts about themselves (prefer get_memories)
- User asks fuzzy/conceptual questions (use semantic_search instead)
- If backend tools are not available, fall back to execute_sql on the local transcription_sessions table

Note: Database is read-only (SELECT only). SELECT queries auto-limit to 200 rows.
Supports FTS5 MATCH queries for keyword search (e.g., WHERE screenshots_fts MATCH 'keyword').

Key tables: screenshots (appName, windowTitle, ocrText, timestamp), transcription_sessions (title, overview, startedAt, finishedAt), transcription_segments (sessionId, speaker, text, startTime), action_items (description, completed, priority, dueAt, category), memories (content, category, source), staged_tasks (description, priority, source), focus_sessions (status, appOrSite, durationSeconds), observations (appName, contextSummary, currentActivity), goals (title, goalType, targetValue, currentValue), indexed_files (path, filename, fileType, folder), live_notes (sessionId, text, timestamp), ai_user_profiles (profileText, generatedAt).`,
    inputSchema: {
      type: "object" as const,
      properties: {
        query: { type: "string" as const, description: "SQL query to execute against omi.db" },
      },
      required: ["query"],
    },
  },
  {
    name: "semantic_search",
    description: `Vector similarity search on the user's screen history (what they saw on their computer).

Use when:
- Fuzzy or conceptual queries where exact SQL keywords won't work
- User asks "when was I reading about X?" or "find where I was working on Y"
- Theme-based recall: "design mockups", "code reviews", "email about project Z"

Don't use when:
- User asks about spoken conversations or transcripts (prefer search_conversations if available)
- User asks for structured counts or stats (use execute_sql)
- User wants a broad daily recap (use get_daily_recap)

Parameter guidance:
- days: Start with 7 (default). Use 1-3 for recent activity, 14-30 for older searches.
- app_filter: Set when user specifies an app (e.g., "in Chrome", "in VS Code"). Omit for cross-app searches.
- Results are ranked by semantic similarity — top 15 returned.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        query: {
          type: "string" as const,
          description: "Natural language search query describing what the user was doing or viewing",
        },
        days: {
          type: "number" as const,
          description: "Days to search back: 1-3 for recent, 7 default, 14-30 for older",
        },
        app_filter: {
          type: "string" as const,
          description: "Filter to a specific app (e.g., 'Chrome', 'VS Code'). Omit for all apps",
        },
      },
      required: ["query"],
    },
  },
  {
    name: "get_daily_recap",
    description: `Get a pre-formatted daily activity recap combining app usage, conversations, tasks, focus sessions, memories, and observations.

Use when:
- User asks "what did I do today/yesterday/this week?"
- Broad activity summaries or daily reviews
- User wants a quick overview without specifying a topic

Don't use when:
- User asks about a specific topic or event (prefer search_conversations if available)
- User needs detailed transcript content (prefer get_conversations if available)
- User wants structured data or counts (use execute_sql)

This tool runs six queries in one call (apps, conversations, tasks, focus, memories, observations) — much faster than multiple execute_sql calls.

Parameter guidance:
- days_ago=0: today's activity so far
- days_ago=1: yesterday (default, most common)
- days_ago=7: past week overview`,
    inputSchema: {
      type: "object" as const,
      properties: {
        days_ago: {
          type: "number" as const,
          description: "0=today, 1=yesterday, 7=past week. Default 1",
        },
      },
      required: [],
    },
  },
  {
    name: "search_tasks",
    description: `Vector similarity search on tasks (action_items + staged_tasks).

Use when:
- User asks to find tasks by meaning or topic, not exact keywords
- e.g. "tasks about shopping", "anything related to the presentation"
- More reliable than hand-writing FTS MATCH queries for task search

Don't use when:
- User wants exact keyword match (use execute_sql with action_items_fts MATCH)
- User wants structured task listing or counts (use execute_sql)

Results are ranked by semantic similarity — top 10 returned.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        query: {
          type: "string" as const,
          description: "Natural language description of the tasks to find",
        },
        include_completed: {
          type: "boolean" as const,
          description: "Include completed tasks in results. Default false",
        },
      },
      required: ["query"],
    },
  },
  {
    name: "complete_task",
    description: `Toggle a task's completion status. Syncs to backend (Firestore).
Use after finding the task with execute_sql. Pass the backendId from the action_items table.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        task_id: {
          type: "string" as const,
          description: "The backendId of the task from action_items table",
        },
      },
      required: ["task_id"],
    },
  },
  {
    name: "delete_task",
    description: `Delete a task permanently. Syncs to backend (Firestore).
Use after finding the task with execute_sql. Pass the backendId from the action_items table.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        task_id: {
          type: "string" as const,
          description: "The backendId of the task from action_items table",
        },
      },
      required: ["task_id"],
    },
  },
  // --- Backend RAG tools (call Python backend /v1/tools/* via Swift) ---
  // Tool order follows backend CORE_TOOLS for prompt cache stability.
  {
    name: "get_conversations",
    description: `Retrieve user conversations from the Omi backend with summaries, action items, and metadata.

Use when:
- User asks about recent conversations, what they discussed, or needs conversation details
- Time-based retrieval: "what did I talk about today?", "conversations from last week"
- Broad activity queries: "what did I do today?" (with start_date=start of today)
- Summarization queries: "summarize my week", "recap my month"

Don't use when:
- User asks about a specific topic or event (use search_conversations — it uses semantic search)
- User asks about preferences or facts about themselves (use get_memories)

Parameter guidance:
- start_date/end_date: MUST be ISO format with timezone offset (e.g. 2024-01-19T15:00:00-08:00). Always include timezone.
- limit: default 20. For summaries/recaps, set limit=5000 to get all conversations in the range.
- include_transcript: default true. When true, loads speaker data for attendee names. Summaries and action items are always included regardless. Set false to skip speaker processing for faster results.
- Prefer narrower time windows first (hours > day > week > month) for better relevance.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        start_date: { type: "string" as const, description: "ISO date with timezone offset (e.g. 2024-01-19T15:00:00-08:00)" },
        end_date: { type: "string" as const, description: "ISO date with timezone offset (e.g. 2024-01-19T23:59:59-08:00)" },
        limit: { type: "number" as const, description: "Number of conversations: 20 default, 5000 for summaries/recaps" },
        offset: { type: "number" as const, description: "Pagination offset (default: 0)" },
        include_transcript: { type: "boolean" as const, description: "Load speaker/attendee data (default: true). Summaries and action items always included. Set false to skip speaker processing." },
      },
      required: [],
    },
  },
  {
    name: "search_conversations",
    description: `Semantic search across user conversations — USE THIS FOR EVENTS AND INCIDENTS.

Uses AI embeddings to find conversations matching a concept, even without exact keywords.

Use when:
- Questions about SPECIFIC EVENTS or INCIDENTS: "when did a dog bite me?", "what happened at the party?"
- Any "when did X happen?" or "what happened when Y?" question
- Searching for concepts, themes, or topics: "discussions about AI", "health-related talks"
- Finding conversations about specific people, places, or things

Don't use when:
- User asks about preferences or facts (use get_memories for "what's my favorite food?", "do I like dogs?")
- Time-based retrieval without a topic (use get_conversations for "what did I do today?")

CRITICAL DISTINCTION:
- "What's my favorite food?" → get_memories (FACT/preference)
- "When did I get food poisoning?" → search_conversations (EVENT)
- "Do I like dogs?" → get_memories (FACT/preference)
- "When did a dog bite me?" → search_conversations (EVENT)

Parameter guidance:
- query: Descriptive phrase about the event or concept — semantic search works best with natural language.
- start_date/end_date: ISO format with timezone offset. Use to narrow the time range when known.
- limit: default 5, max 20. Usually 5 is enough for specific events.
- include_transcript: default true. Loads speaker/attendee data. Summaries and action items are always included. Set false to skip speaker processing for speed.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        query: { type: "string" as const, description: "Natural language description of the event, topic, or concept to search for" },
        start_date: { type: "string" as const, description: "ISO date with timezone offset (e.g. 2024-01-19T00:00:00+07:00)" },
        end_date: { type: "string" as const, description: "ISO date with timezone offset (e.g. 2024-01-31T23:59:59+07:00)" },
        limit: { type: "number" as const, description: "Number of results (default: 5, max: 20)" },
        include_transcript: { type: "boolean" as const, description: "Load speaker/attendee data (default: true). Summaries/action items always included. Set false to skip speaker processing." },
      },
      required: ["query"],
    },
  },
  {
    name: "get_memories",
    description: `Retrieve user memories — static facts, preferences, habits, and personal information.

Use when:
- User asks about their own facts or preferences: "what's my name?", "what do you know about me?"
- Broad self-knowledge queries: "who am I?", "what are my hobbies?"
- Checking stored personal info: relationships, goals, habits

Don't use when:
- User asks about specific events or incidents (use search_conversations for "when did X happen?")
- User asks about conversation content or transcripts (use get_conversations or search_conversations)

CRITICAL: This tool stores FACTS, not EVENTS. "What's my favorite food?" → get_memories. "When did I eat sushi?" → search_conversations.

Parameter guidance:
- limit: default 50. For broad questions ("what do you know about me?"), use limit=5000 to get comprehensive results. For specific narrow topics, 50-200 is enough.
- start_date/end_date: ISO format with timezone offset. Rarely needed — memories are timeless facts.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        limit: { type: "number" as const, description: "Number of memories: 50 default, 5000 for broad questions, 50-200 for specific topics" },
        offset: { type: "number" as const, description: "Pagination offset (default: 0)" },
        start_date: { type: "string" as const, description: "ISO date with timezone offset (rarely needed for memories)" },
        end_date: { type: "string" as const, description: "ISO date with timezone offset (rarely needed for memories)" },
      },
      required: [],
    },
  },
  {
    name: "search_memories",
    description: `Semantic search across user memories/facts. Finds memories matching a concept using AI embeddings.

Use when:
- Searching for memories about a specific topic: "what do I know about cooking?", "my work goals"
- Narrowing down from a broad set of memories to topic-specific ones

Don't use when:
- User wants ALL their memories (use get_memories with high limit)
- User asks about events/incidents (use search_conversations)

Parameter guidance:
- query: Natural language topic to search for. Semantic matching finds conceptually related memories.
- limit: default 5, max 20. Usually 5 is enough for focused queries.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        query: { type: "string" as const, description: "Natural language topic to search for in memories" },
        limit: { type: "number" as const, description: "Number of results (default: 5, max: 20)" },
      },
      required: ["query"],
    },
  },
  {
    name: "get_action_items",
    description: `Retrieve user action items (tasks/to-dos) from the Omi backend.

Use when:
- User asks about tasks: "what are my tasks?", "show my to-dos", "what's due today?"
- Checking task status: "what's pending?", "what did I complete?"

Parameter guidance:
- completed: true=completed only, false=pending only, omit=all tasks
- IMPORTANT: Use due_start_date/due_end_date to filter by due date ("what's due this week?"). Use start_date/end_date to filter by creation date ("tasks created today"). These are different fields.
- All dates: ISO format with timezone offset (e.g. 2024-01-19T00:00:00-08:00).`,
    inputSchema: {
      type: "object" as const,
      properties: {
        limit: { type: "number" as const, description: "Number of items (default: 50, max: 500)" },
        offset: { type: "number" as const, description: "Pagination offset (default: 0)" },
        completed: { type: "boolean" as const, description: "Filter: true=completed, false=pending, omit=all" },
        start_date: { type: "string" as const, description: "Filter by creation date (ISO with timezone offset)" },
        end_date: { type: "string" as const, description: "Filter by creation date (ISO with timezone offset)" },
        due_start_date: { type: "string" as const, description: "Filter by due date (ISO with timezone offset)" },
        due_end_date: { type: "string" as const, description: "Filter by due date (ISO with timezone offset)" },
      },
      required: [],
    },
  },
  {
    name: "create_action_item",
    description: `Create a new action item (task) for the user.

Use when:
- User explicitly asks to create a task: "add task...", "remind me to...", "create a to-do..."

Don't use when:
- User is just discussing tasks without asking to create one
- User wants to view or search existing tasks (use get_action_items)

Parameter guidance:
- description: Keep short (5-10 words). This is what the user sees in their task list.
- due_at: ISO format with timezone offset. Defaults to 24h from now if omitted.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        description: { type: "string" as const, description: "Short task description (5-10 words)" },
        due_at: { type: "string" as const, description: "Due date (ISO with timezone offset, defaults to 24h from now)" },
        conversation_id: { type: "string" as const, description: "Source conversation ID (optional)" },
      },
      required: ["description"],
    },
  },
  {
    name: "update_action_item",
    description: `Update an action item's status, description, or due date.

Use when:
- User wants to complete a task: "mark X as done", "I finished Y"
- User wants to change a task: "change due date to...", "update the description"

Always use get_action_items first to find the action_item_id.

Parameter guidance:
- action_item_id: Required. Get this from get_action_items results.
- completed: true to mark done, false to mark pending.
- due_at: ISO format with timezone offset.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        action_item_id: { type: "string" as const, description: "ID from get_action_items (required)" },
        completed: { type: "boolean" as const, description: "Mark complete (true) or pending (false)" },
        description: { type: "string" as const, description: "New description" },
        due_at: { type: "string" as const, description: "New due date (ISO with timezone offset)" },
      },
      required: ["action_item_id"],
    },
  },
  {
    name: "load_skill",
    description: `Load the full instructions for a named skill. Call this when you decide to use a skill listed in <available_skills>. Returns the complete SKILL.md content with step-by-step instructions and workflows.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        name: {
          type: "string" as const,
          description: "Skill name exactly as listed in available_skills",
        },
      },
      required: ["name"],
    },
  },
  // --- Onboarding tools ---
  {
    name: "check_permission_status",
    description: `Check which macOS permissions are currently granted. Returns JSON with status of all 5 permissions: screen_recording, microphone, notifications, accessibility, automation. Call before requesting permissions.`,
    inputSchema: {
      type: "object" as const,
      properties: {},
      required: [],
    },
  },
  {
    name: "request_permission",
    description: `Request a specific macOS permission from the user. Triggers the macOS system permission dialog. Returns "granted", "pending", or "denied". Call one at a time.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        type: {
          type: "string" as const,
          description:
            "Permission type: screen_recording, microphone, notifications, accessibility, or automation",
        },
      },
      required: ["type"],
    },
  },
  {
    name: "scan_files",
    description: `Scan the user's files. BLOCKING — waits for the scan to complete before returning. Scans ~/Downloads, ~/Documents, ~/Desktop, ~/Developer, ~/Projects, /Applications, and Apple Notes storage folders when available. Returns file type breakdown, project indicators, recent files, installed apps, and existing task candidates when available. Also reports which folders were DENIED access by macOS. If folders were denied, call again after the user grants access.`,
    inputSchema: {
      type: "object" as const,
      properties: {},
      required: [],
    },
  },
  {
    name: "set_user_preferences",
    description: `Save user preferences like language and name. Only call if the user explicitly mentions a preferred language or name correction.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        language: {
          type: "string" as const,
          description: "Language code (e.g. en, es, ja)",
        },
        name: {
          type: "string" as const,
          description: "User's preferred name",
        },
      },
      required: [],
    },
  },
  {
    name: "ask_followup",
    description: `Present a question with quick-reply buttons to the user. The UI renders clickable buttons.
Use in Step 4 (follow-up question after file discoveries) and Step 5 (permission grant buttons).
The user can click a button OR type their own reply. Wait for their response before continuing.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        question: {
          type: "string" as const,
          description: "The question to present to the user",
        },
        options: {
          type: "array" as const,
          items: { type: "string" as const },
          description:
            "2-3 quick-reply button labels. For permissions, include 'Grant [Permission]' and 'Skip'.",
        },
      },
      required: ["question", "options"],
    },
  },
  {
    name: "complete_onboarding",
    description: `Finish onboarding and start the app. Logs analytics, starts background services, enables launch-at-login. Call as the LAST step after permissions are done.`,
    inputSchema: {
      type: "object" as const,
      properties: {},
      required: [],
    },
  },
  {
    name: "save_knowledge_graph",
    description: `Save a knowledge graph of entities and relationships discovered about the user.
Extract people, organizations, projects, tools, languages, frameworks, and concepts.
Build relationships like: works_on, uses, built_with, part_of, knows, etc.
Aim for 15-40 nodes with meaningful edges connecting them.`,
    inputSchema: {
      type: "object" as const,
      properties: {
        nodes: {
          type: "array" as const,
          items: {
            type: "object" as const,
            properties: {
              id: { type: "string" as const },
              label: { type: "string" as const },
              node_type: {
                type: "string" as const,
                enum: ["person", "organization", "place", "thing", "concept"],
              },
              aliases: { type: "array" as const, items: { type: "string" as const } },
            },
            required: ["id", "label", "node_type"],
          },
        },
        edges: {
          type: "array" as const,
          items: {
            type: "object" as const,
            properties: {
              source_id: { type: "string" as const },
              target_id: { type: "string" as const },
              label: { type: "string" as const },
            },
            required: ["source_id", "target_id", "label"],
          },
        },
      },
      required: ["nodes", "edges"],
    },
  },
];

// Filter tools based on session type: onboarding sessions get onboarding tools,
// regular sessions exclude them
const TOOLS = ALL_TOOLS.filter((t) =>
  isOnboarding ? true : !ONBOARDING_TOOL_NAMES.has(t.name)
);

// --- JSON-RPC handling ---

function send(msg: Record<string, unknown>): void {
  try {
    process.stdout.write(JSON.stringify(msg) + "\n");
  } catch (err) {
    logErr(`Failed to write to stdout: ${err}`);
  }
}

async function handleJsonRpc(
  body: Record<string, unknown>
): Promise<void> {
  const id = body.id;
  const method = body.method as string;
  const params = (body.params ?? {}) as Record<string, unknown>;

  // Notifications (no id) don't get responses
  const isNotification = id === undefined || id === null;

  switch (method) {
    case "initialize":
      if (!isNotification) {
        send({
          jsonrpc: "2.0",
          id,
          result: {
            protocolVersion: "2024-11-05",
            capabilities: { tools: {} },
            serverInfo: { name: "omi-tools", version: "1.0.0" },
          },
        });
      }
      break;

    case "notifications/initialized":
      // No response needed
      break;

    case "tools/list":
      if (!isNotification) {
        send({
          jsonrpc: "2.0",
          id,
          result: { tools: TOOLS },
        });
      }
      break;

    case "tools/call": {
      const toolName = params.name as string;
      const args = (params.arguments ?? {}) as Record<string, unknown>;

      if (toolName === "execute_sql") {
        const query = args.query as string;
        if (currentMode === "ask") {
          const normalized = query.trim().toUpperCase();
          if (!normalized.startsWith("SELECT")) {
            if (!isNotification) {
              send({
                jsonrpc: "2.0",
                id,
                result: {
                  content: [
                    {
                      type: "text",
                      text: "Blocked: Only SELECT queries are allowed in Ask mode.",
                    },
                  ],
                },
              });
            }
            return;
          }
        }
        const result = await requestSwiftTool("execute_sql", { query });
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (toolName === "semantic_search") {
        const input: Record<string, unknown> = {
          query: args.query,
          days: args.days ?? 7,
        };
        if (args.app_filter) input.app_filter = args.app_filter;
        const result = await requestSwiftTool("semantic_search", input);
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (toolName === "get_daily_recap") {
        const daysAgo = (args.days_ago as number) ?? 1;
        const result = await requestSwiftTool("get_daily_recap", { days_ago: daysAgo });
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (toolName === "search_tasks") {
        const input: Record<string, unknown> = { query: args.query };
        if (args.include_completed) input.include_completed = args.include_completed;
        const result = await requestSwiftTool("search_tasks", input);
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (toolName === "complete_task") {
        const taskId = args.task_id as string;
        const result = await requestSwiftTool("complete_task", { task_id: taskId });
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (toolName === "delete_task") {
        const taskId = args.task_id as string;
        const result = await requestSwiftTool("delete_task", { task_id: taskId });
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (toolName === "load_skill") {
        const name = (args.name as string || "").trim();
        const workspace = process.env.OMI_WORKSPACE || "";
        const candidates = [
          workspace ? join(workspace, ".claude", "skills", name, "SKILL.md") : "",
          join(homedir(), ".claude", "skills", name, "SKILL.md"),
        ].filter(Boolean);

        let content: string | null = null;
        for (const filePath of candidates) {
          try {
            content = readFileSync(filePath, "utf8");
            logErr(`load_skill: loaded '${name}' from ${filePath}`);
            break;
          } catch {
            // not at this path, try next
          }
        }

        // For dev-mode, prepend workspace path so Claude has that context
        if (content && name === "dev-mode" && workspace) {
          content = `Workspace: ${workspace}\n\n${content}`;
        }

        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: {
              content: [{
                type: "text",
                text: content ?? `Skill '${name}' not found. Check the name matches one listed in <available_skills>.`,
              }],
            },
          });
        }
      } else if (
        toolName === "check_permission_status" ||
        toolName === "request_permission" ||
        toolName === "scan_files" ||
        toolName === "set_user_preferences" ||
        toolName === "ask_followup" ||
        toolName === "complete_onboarding" ||
        toolName === "save_knowledge_graph"
      ) {
        // Onboarding tools — forward directly to Swift
        const result = await requestSwiftTool(toolName, args);
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (
        toolName === "get_conversations" ||
        toolName === "search_conversations" ||
        toolName === "get_memories" ||
        toolName === "search_memories" ||
        toolName === "get_action_items" ||
        toolName === "create_action_item" ||
        toolName === "update_action_item"
      ) {
        // Backend RAG tools — forward to Swift which calls Python backend
        const result = await requestSwiftTool(toolName, args);
        if (!isNotification) {
          send({
            jsonrpc: "2.0",
            id,
            result: { content: [{ type: "text", text: result }] },
          });
        }
      } else if (!isNotification) {
        send({
          jsonrpc: "2.0",
          id,
          error: { code: -32601, message: `Unknown tool: ${toolName}` },
        });
      }
      break;
    }

    default:
      if (!isNotification) {
        send({
          jsonrpc: "2.0",
          id,
          error: { code: -32601, message: `Method not found: ${method}` },
        });
      }
  }
}

// --- Main ---

async function main(): Promise<void> {
  // Connect to parent bridge pipe for tool forwarding
  await connectToPipe();

  // Read JSON-RPC from stdin
  const rl = createInterface({ input: process.stdin, terminal: false });

  rl.on("line", (line: string) => {
    if (!line.trim()) return;
    try {
      const msg = JSON.parse(line) as Record<string, unknown>;
      handleJsonRpc(msg).catch((err) => {
        logErr(`Error handling request: ${err}`);
      });
    } catch {
      logErr(`Invalid JSON: ${line.slice(0, 200)}`);
    }
  });

  rl.on("close", () => {
    process.exit(0);
  });

  logErr("omi-tools stdio MCP server started");
}

main().catch((err) => {
  logErr(`Fatal: ${err}`);
  process.exit(1);
});
