/**
 * Chat context builder.
 *
 * Loads the user's goals, tasks, and memories — from the same sources the
 * Goals/Tasks/Memories pages use — and assembles a system prompt that grounds
 * the chat assistant in real user data. Mirrors `ChatProvider.swift`'s
 * `buildSystemPrompt` flow.
 *
 * Sources:
 *  - Goals:    local SQLite (`get_goals`), populated by `goalStore.loadGoals`
 *              from `/v1/goals/all`.
 *  - Tasks:    backend `/v1/action-items` (same as `taskStore.loadTasks`).
 *  - Memories: backend `/v3/memories` (same as `memoryStore.loadMemories`).
 *
 * Cached per session: the first message in a session pays the load cost,
 * subsequent messages reuse the cached string. The cache is invalidated when
 * the session changes (handled by `chatStore`).
 */

import { invoke } from "@tauri-apps/api/core";

import { api } from "./api";
import { useAuthStore } from "../stores/authStore";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Goal {
  id: string;
  title: string;
  description: string | null;
  goal_type: string;
  target_value: number;
  current_value: number;
  unit: string | null;
  is_active: boolean;
  deleted: boolean;
}

interface ActionItem {
  id: string;
  description: string;
  completed: boolean;
  due_at?: string | null;
}

interface MemoryRecord {
  id: string;
  content: string;
  category?: string;
  structured?: { title?: string; category?: string };
}

// ---------------------------------------------------------------------------
// Defaults
// ---------------------------------------------------------------------------

const BASE_PROMPT =
  "You are Nooto, an AI assistant integrated into the user's desktop app. " +
  "You help with questions about their day, notes, screen activity, goals, tasks, and personal context. " +
  "Use the facts, goals, and tasks below to personalize your answers. Be concise and helpful.";


const TOOL_GUIDANCE = [
  "",
  "You also have these tools available — call them when the answer requires fresher or broader data than the snapshot above, or when the user asks you to take an action:",
  "",
  "Read tools:",
  "- search_tasks(query?, completed?, limit?) — full task list (the snapshot only includes the top open ones).",
  "- search_memories(query?, limit?) — full memory store, keyword-filtered.",
  "- search_goals(query?, active_only?) — all goals including completed.",
  "- search_screen_history(query, limit?) — semantic search over older screen captures, for conceptual lookups ('when was I researching X', 'find that article about Y').",
  "- get_recent_screen_activity(limit?, since_minutes?, app_name_contains?) — pulls the literal OCR text of recent on-screen content. ALWAYS call this for any question about what the user just typed/asked/said/saw/did, or what is on a specific app right now. Use since_minutes to scope ('1 minute ago' → since_minutes=2 to be safe) and app_name_contains to target an app ('Claude Code' lives inside Ghostty/terminal apps; browsers are 'chrome'/'safari'/'arc'). Don't claim you can't see the user's recent activity without calling this first.",
  "",
  "Write tools (act on the user's behalf — confirm intent first if the request is ambiguous):",
  "- create_task(description, due_at?) — add a new task. due_at is an ISO 8601 timestamp; resolve relative phrases like 'tomorrow' to absolute dates yourself.",
  "- update_task(id, description?, due_at?) — change a task's description and/or due date. Pass empty string for due_at to clear it. Look up the id with search_tasks first.",
  "- complete_task(id, completed) — toggle done/open. Look up the id with search_tasks first.",
  "- delete_task(id) — delete a task.",
  "- create_goal(title, description?, goal_type?, target_value?, unit?) — add a new goal. Default goal_type is 'numeric'.",
  "- update_goal_progress(id, current_value) — set a goal's progress. Use search_goals to find the id.",
  "- add_memory(content, category?) — save a personal fact when the user asks you to remember something or shares a durable fact.",
  "",
  "Prefer the snapshot for short, direct questions. Reach for read tools when the user asks about something not visible above, and write tools when they want to create, change, or delete.",
].join("\n");

const MAX_MEMORIES = 30;
const MAX_TASKS = 20;

// ---------------------------------------------------------------------------
// Loaders — each isolated so one failure doesn't block the others
// ---------------------------------------------------------------------------

async function loadMemories(): Promise<MemoryRecord[]> {
  try {
    const data = await api.get<MemoryRecord[]>("/v3/memories?limit=50&offset=0");
    if (!Array.isArray(data)) return [];
    return data.slice(0, MAX_MEMORIES);
  } catch (err) {
    console.warn("[chatContext] failed to load memories", err);
    return [];
  }
}

async function loadGoals(): Promise<Goal[]> {
  try {
    const all = await invoke<Goal[]>("get_goals");
    return all.filter((g) => !g.deleted && g.is_active);
  } catch (err) {
    console.warn("[chatContext] failed to load goals", err);
    return [];
  }
}

async function loadTasks(): Promise<ActionItem[]> {
  try {
    const data = await api.get<{ action_items: ActionItem[]; has_more: boolean }>(
      "/v1/action-items",
    );
    const items = data?.action_items ?? [];
    return items.filter((t) => !t.completed).slice(0, MAX_TASKS);
  } catch (err) {
    console.warn("[chatContext] failed to load tasks", err);
    return [];
  }
}

// ---------------------------------------------------------------------------
// Formatters — XML sections matching ChatProvider.swift's prompt vocabulary
// ---------------------------------------------------------------------------

function formatMemoriesSection(memories: MemoryRecord[], userLabel: string): string {
  if (memories.length === 0) return "";
  const lines = ["<user_facts>", `Facts about ${userLabel}:`];
  for (const m of memories) {
    if (!m.content) continue;
    lines.push(`- ${m.content}`);
  }
  lines.push("</user_facts>");
  return lines.join("\n");
}

function formatGoalsSection(goals: Goal[]): string {
  if (goals.length === 0) return "";
  const lines = ["<user_goals>"];
  for (const g of goals) {
    let line = `- ${g.title}`;
    if (g.description && g.description.trim().length > 0) {
      line += `: ${g.description}`;
    }
    if (g.goal_type !== "boolean") {
      const cur = Math.round(g.current_value);
      const tgt = Math.round(g.target_value);
      line += ` (progress: ${cur}/${tgt}`;
      if (g.unit && g.unit.trim().length > 0) line += ` ${g.unit}`;
      line += ")";
    }
    lines.push(line);
  }
  lines.push("</user_goals>");
  return lines.join("\n");
}

function formatTasksSection(tasks: ActionItem[]): string {
  if (tasks.length === 0) return "";
  const lines = ["<user_tasks>", "Current tasks:"];
  for (const t of tasks) {
    let line = `- ${t.description}`;
    if (t.due_at) {
      const d = new Date(t.due_at);
      if (!Number.isNaN(d.getTime())) {
        line += ` [due: ${d.toLocaleString()}]`;
      }
    }
    lines.push(line);
  }
  lines.push("</user_tasks>");
  return lines.join("\n");
}

function deriveUserLabel(): string {
  const email = useAuthStore.getState().userEmail;
  if (!email) return "the user";
  const local = email.split("@")[0];
  return local || "the user";
}

// ---------------------------------------------------------------------------
// Cache & public API
// ---------------------------------------------------------------------------

export interface ContextSnapshot {
  text: string;
  counts: { memories: number; goals: number; tasks: number };
}

const cache = new Map<string, ContextSnapshot>();
const inflight = new Map<string, Promise<ContextSnapshot>>();

function formatNowSection(): string {
  const now = new Date();
  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "local";
  return [
    "<current_time>",
    `Now: ${now.toString()} (timezone: ${tz}, ISO: ${now.toISOString()})`,
    "Use this to resolve relative dates like 'tomorrow' or 'next Monday' when calling tools.",
    "</current_time>",
  ].join("\n");
}

async function buildContextSnapshot(sessionId: string): Promise<ContextSnapshot> {
  const cached = cache.get(sessionId);
  if (cached) return cached;

  const pending = inflight.get(sessionId);
  if (pending) return pending;

  const promise = (async () => {
    const [memories, goals, tasks] = await Promise.all([
      loadMemories(),
      loadGoals(),
      loadTasks(),
    ]);

    const sections = [
      formatNowSection(),
      formatMemoriesSection(memories, deriveUserLabel()),
      formatGoalsSection(goals),
      formatTasksSection(tasks),
    ].filter((s) => s.length > 0);

    const snapshot: ContextSnapshot = {
      text: sections.length === 0 ? "" : sections.join("\n\n"),
      counts: {
        memories: memories.length,
        goals: goals.length,
        tasks: tasks.length,
      },
    };

    console.info(
      `[chatContext] built prompt for session ${sessionId}: ` +
        `${memories.length} memories, ${goals.length} goals, ${tasks.length} tasks`,
    );

    cache.set(sessionId, snapshot);
    return snapshot;
  })();

  inflight.set(sessionId, promise);
  try {
    return await promise;
  } finally {
    inflight.delete(sessionId);
  }
}

/** Returns just the counts (and triggers the snapshot load if not cached).
 *  Used by the chatStore to render the "Loaded context" preamble card. */
export async function getContextSnapshotCounts(sessionId: string) {
  const snap = await buildContextSnapshot(sessionId);
  return snap.counts;
}

/** System prompt for the Gemini path (tool calling enabled). */
export async function buildChatSystemPrompt(sessionId: string): Promise<string> {
  const snapshot = await buildContextSnapshot(sessionId);
  const body = snapshot.text ? `${BASE_PROMPT}\n\n${snapshot.text}` : BASE_PROMPT;
  return `${body}\n${TOOL_GUIDANCE}`;
}

/** System prompt for the Claude tool-use path. Same context snapshot plus
 *  tool affordance guidance so the LLM knows when to call vs. answer from
 *  the snapshot. */
export async function buildClaudeChatSystemPrompt(sessionId: string): Promise<string> {
  const snapshot = await buildContextSnapshot(sessionId);
  const body = snapshot.text ? `${BASE_PROMPT}\n\n${snapshot.text}` : BASE_PROMPT;
  return `${body}\n${TOOL_GUIDANCE}`;
}

export function invalidateChatContext(sessionId?: string): void {
  if (sessionId) {
    cache.delete(sessionId);
  } else {
    cache.clear();
  }
}
