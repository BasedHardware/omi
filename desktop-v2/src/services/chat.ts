/**
 * Chat service — Anthropic SDK with local tool execution.
 *
 * When the user has connected their Claude account (OAuth), chat runs through
 * the Anthropic SDK with a tool surface that mirrors the Swift desktop app:
 * the LLM can issue function calls to query goals/tasks/memories, search the
 * user's screen capture history, and mutate tasks. Each tool call routes to
 * a Tauri invoke or a backend REST call.
 *
 * NOTE: `dangerouslyAllowBrowser: true` is required because Tauri WebViews
 * run in a browser context. The OAuth token is stored locally via
 * tauri-plugin-store and never leaves the device.
 */

import Anthropic from "@anthropic-ai/sdk";
import { invoke } from "@tauri-apps/api/core";

import { api } from "@/services/api";
import { invalidateChatContext } from "@/services/chatContext";
import { embedText } from "@/services/embeddingService";
import {
  getRecentScreenshots,
  searchScreenshots,
  searchScreenshotsSemantic,
} from "@/services/rewind";
import type { ScreenshotRow, SemanticHit } from "@/services/rewind";
import { useGoalStore } from "@/stores/goalStore";
import { useMemoryStore } from "@/stores/memoryStore";
import { useTaskStore } from "@/stores/taskStore";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ToolCallRecord {
  id: string;
  name: string;
  input: unknown;
  output?: string;
}

interface Goal {
  id: string;
  title: string;
  description: string | null;
  goal_type: string;
  target_value: number;
  current_value: number;
  unit: string | null;
  is_active: boolean;
  completed_at: string | null;
  deleted: boolean;
}

interface ActionItem {
  id: string;
  description: string;
  completed: boolean;
  due_at?: string | null;
  created_at?: string | null;
}

interface MemoryRecord {
  id: string;
  content: string;
  category?: string;
  created_at?: string;
}

// ---------------------------------------------------------------------------
// Tool definitions exposed to the LLM
// ---------------------------------------------------------------------------

export const CHAT_TOOLS: Anthropic.Tool[] = [
  {
    name: "search_tasks",
    description:
      "Search the user's action items (tasks). Returns up to `limit` tasks " +
      "filtered by completion status and matching the optional keyword query " +
      "(case-insensitive substring match against the description). Each result " +
      "includes the task's id — use that id with `complete_task` or `delete_task`.",
    input_schema: {
      type: "object" as const,
      properties: {
        query: { type: "string", description: "Optional keyword to filter task descriptions" },
        completed: {
          type: "boolean",
          description: "If true, only return completed tasks; if false, only open ones; omit for both",
        },
        limit: { type: "number", description: "Max results (default 20)" },
      },
      required: [],
    },
  },
  {
    name: "search_memories",
    description:
      "Search the user's stored memories/facts (their personal knowledge base). " +
      "Returns up to `limit` memories matching the optional keyword query. " +
      "Use this to find facts the user has previously mentioned or that have been extracted from their activity.",
    input_schema: {
      type: "object" as const,
      properties: {
        query: { type: "string", description: "Optional keyword to filter memory content" },
        limit: { type: "number", description: "Max results (default 20)" },
      },
      required: [],
    },
  },
  {
    name: "search_goals",
    description:
      "Search the user's goals. Returns goals filtered by active/completed state and optional keyword. " +
      "Numeric goals include current and target values.",
    input_schema: {
      type: "object" as const,
      properties: {
        query: { type: "string", description: "Optional keyword filter" },
        active_only: { type: "boolean", description: "If true, exclude completed goals (default true)" },
      },
      required: [],
    },
  },
  {
    name: "search_screen_history",
    description:
      "Semantic search over the user's screen capture history (OCR + window titles). " +
      "Use for conceptual lookups like 'when was I researching X' — matches by meaning, not exact words. " +
      "Returns timestamps, app names, window titles, and OCR snippets.",
    input_schema: {
      type: "object" as const,
      properties: {
        query: { type: "string", description: "What to search for (concept or topic)" },
        limit: { type: "number", description: "Max results (default 10)" },
      },
      required: ["query"],
    },
  },
  {
    name: "get_recent_screen_activity",
    description:
      "Return recent screen capture rows (newest first), with OCR text included. " +
      "ALWAYS prefer this tool over guessing for any question about what the user " +
      "just typed, said, asked, did, saw, or was working on in the last few minutes — " +
      "the OCR contains literal on-screen text including prompts the user wrote into " +
      "any app. Combine since_minutes (recency window) with app_name_contains (case-" +
      "insensitive substring of the app, e.g. 'ghostty' for terminals running Claude " +
      "Code, 'chrome' for browser tabs) to scope the slice you need before answering.",
    input_schema: {
      type: "object" as const,
      properties: {
        limit: { type: "number", description: "Max rows to return after filtering (default 30)" },
        since_minutes: {
          type: "number",
          description:
            "Only return shots from the last N minutes. Use small values (1–5) for " +
            "'just now' / 'a minute ago', larger for 'in the last hour'.",
        },
        app_name_contains: {
          type: "string",
          description:
            "Case-insensitive substring filter on app_name. Examples: 'ghostty' for " +
            "terminal/Claude Code, 'chrome'/'safari' for browser, 'code' for VS Code.",
        },
      },
      required: [],
    },
  },
  {
    name: "complete_task",
    description:
      "Toggle a task's completion state. Look up the task id with `search_tasks` first.",
    input_schema: {
      type: "object" as const,
      properties: {
        id: { type: "string", description: "The task id from search_tasks" },
        completed: { type: "boolean", description: "True to mark complete, false to reopen" },
      },
      required: ["id", "completed"],
    },
  },
  {
    name: "delete_task",
    description: "Delete a task by id. Look up the id with `search_tasks` first.",
    input_schema: {
      type: "object" as const,
      properties: {
        id: { type: "string", description: "The task id from search_tasks" },
      },
      required: ["id"],
    },
  },
  {
    name: "create_task",
    description:
      "Create a new task (action item) for the user. Use a clear, action-oriented description. " +
      "Optionally set a due date as an ISO 8601 timestamp (resolve relative phrases like 'tomorrow', 'next Monday', " +
      "'in 2 hours' to an absolute UTC timestamp using the current local time).",
    input_schema: {
      type: "object" as const,
      properties: {
        description: {
          type: "string",
          description: "What the user needs to do, written as a short imperative ('Reply to Anna', 'Buy milk')",
        },
        due_at: {
          type: "string",
          description:
            "Optional ISO 8601 timestamp (e.g. '2026-04-21T17:00:00Z') for when the task is due.",
        },
      },
      required: ["description"],
    },
  },
  {
    name: "update_task",
    description:
      "Update an existing task — change its description and/or due date. Look up the task id with `search_tasks` first. " +
      "Pass only the fields you want to change. To clear a due date, pass due_at as an empty string.",
    input_schema: {
      type: "object" as const,
      properties: {
        id: { type: "string", description: "The task id from search_tasks" },
        description: { type: "string", description: "New description (optional)" },
        due_at: {
          type: "string",
          description:
            "New due date as ISO 8601 timestamp. Pass an empty string to clear the existing due date.",
        },
      },
      required: ["id"],
    },
  },
  {
    name: "create_goal",
    description:
      "Create a new goal. Goal types: 'boolean' (done/not done), 'scale' (1–N rating like sleep quality), 'numeric' (counted units like steps). " +
      "For boolean goals, omit target_value. For scale/numeric, set target_value (and unit if relevant).",
    input_schema: {
      type: "object" as const,
      properties: {
        title: { type: "string", description: "Short title shown in the goals list" },
        description: { type: "string", description: "Optional longer description" },
        goal_type: {
          type: "string",
          enum: ["boolean", "scale", "numeric"],
          description: "How progress is tracked. Default 'numeric'.",
        },
        target_value: { type: "number", description: "Target to reach (e.g. 10000 steps, 8 hours)" },
        unit: { type: "string", description: "Unit label (e.g. 'steps', 'hours', 'pages')" },
      },
      required: ["title"],
    },
  },
  {
    name: "update_goal_progress",
    description:
      "Set a goal's current progress to a specific value. Use after `search_goals` to find the id. " +
      "For numeric/scale goals: set current_value to the new total (not delta). " +
      "For boolean goals: pass 1 to mark done, 0 to mark not done.",
    input_schema: {
      type: "object" as const,
      properties: {
        id: { type: "string", description: "The goal id from search_goals" },
        current_value: { type: "number", description: "New current value" },
      },
      required: ["id", "current_value"],
    },
  },
  {
    name: "add_memory",
    description:
      "Save a personal fact or piece of knowledge about the user to their memory store. " +
      "Use when the user explicitly asks you to remember something, or when they share a durable fact about themselves.",
    input_schema: {
      type: "object" as const,
      properties: {
        content: { type: "string", description: "The fact, in plain prose ('Prefers tea over coffee')" },
        category: {
          type: "string",
          description: "Optional category bucket. Defaults to 'interesting'.",
        },
      },
      required: ["content"],
    },
  },
];

// ---------------------------------------------------------------------------
// Client factory
// ---------------------------------------------------------------------------

export function createClient(accessToken: string): Anthropic {
  return new Anthropic({
    apiKey: "unused",
    authToken: accessToken,
    dangerouslyAllowBrowser: true,
  });
}

// ---------------------------------------------------------------------------
// Tool executors
// ---------------------------------------------------------------------------

// Per-shot OCR cap. Vision .accurate routinely produces 2–4KB per shot; the
// old 280-char cutoff was hiding the user's actual typed prompt inside long
// terminal/IDE captures. 2000 chars × ~30 shots ≈ 60KB, well within budget.
const OCR_SNIPPET_CAP = 2000;

function fmtScreenshotRows(rows: ScreenshotRow[]): string {
  if (rows.length === 0) return "No screen activity found.";
  return rows
    .map((r, i) => {
      const ts = new Date(r.timestamp).toLocaleString();
      const ocr = r.ocr_text ? `\n  Text: ${r.ocr_text.slice(0, OCR_SNIPPET_CAP)}` : "";
      return `${i + 1}. [${ts}] ${r.app_name} — ${r.window_title}${ocr}`;
    })
    .join("\n\n");
}

async function execSearchTasks(args: Record<string, unknown>): Promise<string> {
  const query = typeof args.query === "string" ? args.query.toLowerCase().trim() : "";
  const limit = typeof args.limit === "number" ? args.limit : 20;
  const completedFilter = typeof args.completed === "boolean" ? args.completed : undefined;

  const data = await api.get<{ action_items: ActionItem[]; has_more: boolean }>(
    "/v1/action-items",
  );
  const items = data?.action_items ?? [];
  const filtered = items
    .filter((t) => (completedFilter === undefined ? true : t.completed === completedFilter))
    .filter((t) => (query ? t.description.toLowerCase().includes(query) : true))
    .slice(0, limit);

  if (filtered.length === 0) return "No tasks found.";
  return filtered
    .map((t, i) => {
      const status = t.completed ? "✓" : "○";
      const due = t.due_at ? ` (due ${new Date(t.due_at).toLocaleString()})` : "";
      return `${i + 1}. ${status} [id=${t.id}] ${t.description}${due}`;
    })
    .join("\n");
}

async function execSearchMemories(args: Record<string, unknown>): Promise<string> {
  const query = typeof args.query === "string" ? args.query.toLowerCase().trim() : "";
  const limit = typeof args.limit === "number" ? args.limit : 20;

  const data = await api.get<MemoryRecord[]>("/v3/memories?limit=100&offset=0");
  const items = Array.isArray(data) ? data : [];
  const filtered = items
    .filter((m) => (query ? (m.content ?? "").toLowerCase().includes(query) : true))
    .slice(0, limit);

  if (filtered.length === 0) return "No memories found.";
  return filtered.map((m, i) => `${i + 1}. ${m.content}`).join("\n");
}

async function execSearchGoals(args: Record<string, unknown>): Promise<string> {
  const query = typeof args.query === "string" ? args.query.toLowerCase().trim() : "";
  const activeOnly = typeof args.active_only === "boolean" ? args.active_only : true;

  const all = await invoke<Goal[]>("get_goals");
  const filtered = all
    .filter((g) => !g.deleted)
    .filter((g) => (activeOnly ? g.is_active : true))
    .filter((g) =>
      query
        ? g.title.toLowerCase().includes(query) ||
          (g.description ?? "").toLowerCase().includes(query)
        : true,
    );

  if (filtered.length === 0) return "No goals found.";
  return filtered
    .map((g, i) => {
      let line = `${i + 1}. ${g.title}`;
      if (g.description) line += `: ${g.description}`;
      if (g.goal_type !== "boolean") {
        line += ` (${Math.round(g.current_value)}/${Math.round(g.target_value)}`;
        if (g.unit) line += ` ${g.unit}`;
        line += ")";
      }
      if (!g.is_active) line += " [completed]";
      return line;
    })
    .join("\n");
}

async function execSearchScreenHistory(args: Record<string, unknown>): Promise<string> {
  const query = String(args.query ?? "").trim();
  const limit = typeof args.limit === "number" ? args.limit : 10;
  if (!query) return "Empty query.";

  // Try semantic first; fall back to FTS if embeddings are unavailable.
  try {
    const queryVec = await embedText(query, "RETRIEVAL_QUERY");
    const hits: SemanticHit[] = await searchScreenshotsSemantic(queryVec, limit, 0.45);
    if (hits.length === 0) {
      const ftsRows = await searchScreenshots(query, limit);
      return fmtScreenshotRows(ftsRows);
    }
    const rows = await Promise.all(
      hits.map((h) =>
        invoke<ScreenshotRow | null>("plugin:screen-capture|get_screenshot_by_id", { id: h.id }),
      ),
    );
    const filtered = rows.filter((r): r is ScreenshotRow => r !== null);
    return fmtScreenshotRows(filtered);
  } catch {
    const ftsRows = await searchScreenshots(query, limit);
    return fmtScreenshotRows(ftsRows);
  }
}

async function execGetRecentActivity(args: Record<string, unknown>): Promise<string> {
  const limit = typeof args.limit === "number" ? args.limit : 30;
  const sinceMinutes = typeof args.since_minutes === "number" ? args.since_minutes : undefined;
  const appNameContains =
    typeof args.app_name_contains === "string" ? args.app_name_contains.toLowerCase().trim() : "";

  // Filter TS-side: fetch a generous pool, then narrow. At ~3s capture
  // cadence, 300 rows ≈ 15 min of raw activity.
  const pool = Math.max(limit, 300);
  const all = await getRecentScreenshots(pool, 0);

  const cutoff = sinceMinutes !== undefined ? Date.now() - sinceMinutes * 60_000 : null;
  const filtered = all
    .filter((r) => cutoff === null || new Date(r.timestamp).getTime() >= cutoff)
    .filter((r) => !appNameContains || r.app_name.toLowerCase().includes(appNameContains))
    .slice(0, limit);

  return fmtScreenshotRows(filtered);
}

async function execCompleteTask(args: Record<string, unknown>): Promise<string> {
  const id = String(args.id ?? "");
  const completed = Boolean(args.completed);
  if (!id) return "Missing task id.";
  await api.patch(`/v1/action-items/${id}`, { completed });
  return `Task ${id} marked ${completed ? "complete" : "open"}.`;
}

async function execDeleteTask(args: Record<string, unknown>): Promise<string> {
  const id = String(args.id ?? "");
  if (!id) return "Missing task id.";
  await api.delete(`/v1/action-items/${id}`);
  return `Task ${id} deleted.`;
}

async function execCreateTask(args: Record<string, unknown>): Promise<string> {
  const description = String(args.description ?? "").trim();
  if (!description) return "Missing description.";
  const dueAtRaw = typeof args.due_at === "string" ? args.due_at.trim() : "";
  const body: { description: string; due_at?: string } = { description };
  if (dueAtRaw) body.due_at = dueAtRaw;
  const created = await api.post<ActionItem>("/v1/action-items", body);
  const dueSuffix = created.due_at
    ? ` (due ${new Date(created.due_at).toLocaleString()})`
    : "";
  return `Created task "${created.description}"${dueSuffix} (id=${created.id}).`;
}

async function execUpdateTask(args: Record<string, unknown>): Promise<string> {
  const id = String(args.id ?? "");
  if (!id) return "Missing task id.";

  const body: { description?: string; due_at?: string | null } = {};
  if (typeof args.description === "string" && args.description.trim()) {
    body.description = args.description.trim();
  }
  if (typeof args.due_at === "string") {
    // Empty string explicitly clears the due date; non-empty sets it.
    body.due_at = args.due_at.trim() === "" ? null : args.due_at.trim();
  }
  if (Object.keys(body).length === 0) {
    return "Nothing to update — pass at least one of description or due_at.";
  }

  const updated = await api.patch<ActionItem>(`/v1/action-items/${id}`, body);
  const parts: string[] = [];
  if (body.description !== undefined) parts.push(`description="${updated.description}"`);
  if (body.due_at !== undefined) {
    parts.push(
      updated.due_at
        ? `due=${new Date(updated.due_at).toLocaleString()}`
        : "due cleared",
    );
  }
  return `Updated task ${id}: ${parts.join(", ")}.`;
}

async function execCreateGoal(args: Record<string, unknown>): Promise<string> {
  const title = String(args.title ?? "").trim();
  if (!title) return "Missing title.";

  const goalType = (args.goal_type as string | undefined) ?? "numeric";
  const targetRaw = args.target_value;
  const target = typeof targetRaw === "number" ? targetRaw : goalType === "boolean" ? 1 : 10;
  const unit = (args.unit as string | undefined) ?? null;
  const description = (args.description as string | undefined) ?? null;

  const body = {
    title,
    goal_type: goalType,
    target_value: target,
    current_value: 0,
    min_value: 0,
    max_value: goalType === "boolean" ? 1 : target,
    unit,
  };

  const created = await api.post<{
    id: string;
    title: string;
    description: string | null;
    goal_type: string;
    target_value: number;
    current_value: number;
    min_value: number;
    max_value: number;
    unit: string | null;
    is_active: boolean;
    completed_at: string | null;
  }>("/v1/goals", body);

  await invoke("upsert_goal", {
    input: {
      id: created.id,
      backend_id: created.id,
      backend_synced: true,
      title: created.title,
      description: description,
      goal_type: created.goal_type,
      target_value: created.target_value,
      current_value: created.current_value,
      min_value: created.min_value,
      max_value: created.max_value,
      unit: created.unit,
      is_active: created.is_active,
      completed_at: created.completed_at,
      source: "user",
    },
  });

  return `Created goal "${created.title}" (id=${created.id}).`;
}

async function execUpdateGoalProgress(args: Record<string, unknown>): Promise<string> {
  const id = String(args.id ?? "");
  const currentValue = typeof args.current_value === "number" ? args.current_value : NaN;
  if (!id) return "Missing goal id.";
  if (Number.isNaN(currentValue)) return "Missing or invalid current_value.";

  await invoke("update_goal_progress", { id, currentValue }).catch(() => {});
  await api.patch(`/v1/goals/${id}/progress?current_value=${currentValue}`, {});
  return `Goal ${id} progress set to ${currentValue}.`;
}

async function execAddMemory(args: Record<string, unknown>): Promise<string> {
  const content = String(args.content ?? "").trim();
  if (!content) return "Missing content.";
  const category = String(args.category ?? "interesting");

  const payload = {
    content,
    visibility: "private",
    category,
    confidence: null,
    source_app: null,
    context_summary: null,
    tags: [] as string[],
    reasoning: "",
    current_activity: null,
    source: "chat",
    window_title: null,
    headline: "",
  };

  const resp = await api.post<{ id?: string }>("/v3/memories", payload);
  return resp?.id ? `Saved memory (id=${resp.id}).` : "Saved memory.";
}

/** Tools that mutate user-visible state. After they succeed we refresh the
 *  matching Zustand store so the Tasks/Goals/Memories pages reflect the
 *  change immediately without a manual reload. Errors are swallowed — the
 *  mutation already succeeded; a failed refresh is non-critical. */
const POST_MUTATION_REFRESH: Record<string, () => Promise<void>> = {
  create_task: () => useTaskStore.getState().loadTasks(),
  update_task: () => useTaskStore.getState().loadTasks(),
  complete_task: () => useTaskStore.getState().loadTasks(),
  delete_task: () => useTaskStore.getState().loadTasks(),
  create_goal: () => useGoalStore.getState().loadGoals(true),
  update_goal_progress: () => useGoalStore.getState().loadGoals(true),
  add_memory: () => useMemoryStore.getState().loadMemories(),
};

async function maybeRefreshStores(name: string): Promise<void> {
  const refresh = POST_MUTATION_REFRESH[name];
  if (!refresh) return;
  // Invalidate the per-session prompt cache so the next chat turn sees the
  // updated snapshot (otherwise the model would still answer from stale data).
  invalidateChatContext();
  try {
    await refresh();
  } catch (err) {
    console.warn(`[chat] post-mutation refresh for ${name} failed`, err);
  }
}

export async function executeToolCall(name: string, input: unknown): Promise<string> {
  const args = (input ?? {}) as Record<string, unknown>;
  try {
    const result = await runTool(name, args);
    await maybeRefreshStores(name);
    return result;
  } catch (err) {
    return `Tool ${name} failed: ${err instanceof Error ? err.message : String(err)}`;
  }
}

async function runTool(name: string, args: Record<string, unknown>): Promise<string> {
  switch (name) {
    case "search_tasks":
      return await execSearchTasks(args);
    case "search_memories":
      return await execSearchMemories(args);
    case "search_goals":
      return await execSearchGoals(args);
    case "search_screen_history":
      return await execSearchScreenHistory(args);
    case "get_recent_screen_activity":
      return await execGetRecentActivity(args);
    case "complete_task":
      return await execCompleteTask(args);
    case "delete_task":
      return await execDeleteTask(args);
    case "create_task":
      return await execCreateTask(args);
    case "update_task":
      return await execUpdateTask(args);
    case "create_goal":
      return await execCreateGoal(args);
    case "update_goal_progress":
      return await execUpdateGoalProgress(args);
    case "add_memory":
      return await execAddMemory(args);
    default:
      return `Unknown tool: ${name}`;
  }
}

// ---------------------------------------------------------------------------
// Streaming with tool-use loop
// ---------------------------------------------------------------------------

const MAX_TOOL_ITERATIONS = 6;
const DEFAULT_MODEL = "claude-sonnet-4-20250514";

export async function sendMessageStreaming(
  client: Anthropic,
  messages: Anthropic.MessageParam[],
  systemPrompt: string,
  onTextDelta: (text: string) => void,
  onToolCall?: (id: string, name: string, input: unknown) => void,
  onToolResult?: (id: string, name: string, output: string) => void,
): Promise<{ fullText: string; toolCalls: ToolCallRecord[] }> {
  const allToolCalls: ToolCallRecord[] = [];
  let fullText = "";
  const currentMessages = [...messages];

  for (let iter = 0; iter < MAX_TOOL_ITERATIONS; iter++) {
    const stream = client.messages.stream({
      model: DEFAULT_MODEL,
      max_tokens: 4096,
      system: systemPrompt,
      tools: CHAT_TOOLS,
      messages: currentMessages,
    });

    for await (const event of stream) {
      if (event.type === "content_block_delta" && event.delta.type === "text_delta") {
        fullText += event.delta.text;
        onTextDelta(event.delta.text);
      }
    }

    const finalMessage = await stream.finalMessage();

    if (finalMessage.stop_reason !== "tool_use") break;

    const toolUseBlocks = finalMessage.content.filter(
      (b): b is Anthropic.ToolUseBlock => b.type === "tool_use",
    );
    if (toolUseBlocks.length === 0) break;

    currentMessages.push({ role: "assistant", content: finalMessage.content });

    const toolResults: Anthropic.ToolResultBlockParam[] = [];
    for (const block of toolUseBlocks) {
      onToolCall?.(block.id, block.name, block.input);
      const output = await executeToolCall(block.name, block.input);
      onToolResult?.(block.id, block.name, output);

      allToolCalls.push({ id: block.id, name: block.name, input: block.input, output });
      toolResults.push({ type: "tool_result", tool_use_id: block.id, content: output });
    }

    currentMessages.push({ role: "user", content: toolResults });
  }

  return { fullText, toolCalls: allToolCalls };
}
