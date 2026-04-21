/**
 * TaskDeduplicationService — TypeScript port of
 * `desktop/Desktop/Sources/ProactiveAssistants/Assistants/TaskExtraction/TaskDeduplicationService.swift`.
 *
 * Periodically scans locally-stored staged tasks and asks Gemini to collapse
 * semantic duplicates. Only operates on `staged_tasks` — never touches
 * promoted action_items.
 *
 * Schedule (Swift parity):
 * - Startup delay: 60s
 * - Run interval: every 1 hour
 * - Cooldown: 30 minutes (skip if last run < 30 min ago)
 * - Minimum tasks: 3 (skip if the staged queue is smaller)
 *
 * Uses Gemini's JSON response schema (no tool calls). Hard-deletes duplicates
 * locally, mirrors the delete to the backend by `backend_id`, and audits each
 * deletion via `insert_dedup_log`.
 */

import { invoke } from "@tauri-apps/api/core";
import { api } from "@/services/api";

const INTERVAL_MS = 60 * 60 * 1000; // 1 hour
const STARTUP_DELAY_MS = 60 * 1000; // 60s
const COOLDOWN_MS = 30 * 60 * 1000; // 30 min
const MINIMUM_TASK_COUNT = 3;
const GEMINI_MODEL = "gemini-pro-latest";
const GEMINI_PATH = `/v1/proxy/gemini/models/${GEMINI_MODEL}:generateContent`;

interface RustStagedTask {
  id: string;
  description: string;
  priority: string | null;
  due_at: string | null;
  source_app: string | null;
  created_at: string;
  backend_id: string | null;
  deleted: boolean;
  completed: boolean;
}

interface DedupGroup {
  keep_id: string;
  delete_ids: string[];
  reason: string;
}

interface DedupResponse {
  has_duplicates: boolean;
  duplicate_groups: DedupGroup[];
}

interface GeminiJsonResponse {
  candidates?: Array<{
    content?: { parts?: Array<{ text?: string }> };
  }>;
}

let timerId: ReturnType<typeof setTimeout> | null = null;
let lastRunAt = 0;
let running = false;

function buildPrompt(tasks: RustStagedTask[]): string {
  const lines = tasks.map((t) => {
    const parts = [`ID: ${t.id}`, `Description: ${t.description}`];
    if (t.due_at) parts.push(`Due: ${t.due_at}`);
    if (t.priority) parts.push(`Priority: ${t.priority}`);
    if (t.source_app) parts.push(`Source: ${t.source_app}`);
    parts.push(`Created: ${t.created_at}`);
    return parts.join("\n");
  });
  return [
    "Analyze the following tasks for semantic duplicates. Two tasks are duplicates if they refer to the same action, even if worded differently.",
    "",
    "Tasks:",
    lines.join("\n"),
    "",
    "For each group of duplicates, pick the best task to KEEP based on these criteria (in order):",
    "1. Most descriptive/specific wording",
    "2. Has a due date over one that doesn't",
    "3. Higher priority set (high > medium > low > none)",
    "4. More reliable source (manual > transcription > screenshot)",
    "5. Most recently created",
    "",
    "Only flag tasks as duplicates if you are confident they refer to the same action. When in doubt, do NOT flag as duplicates.",
  ].join("\n");
}

const SYSTEM_PROMPT =
  "You are a task deduplication assistant. You identify semantically duplicate tasks and choose the best one to keep. Be conservative - only flag clear duplicates. Return has_duplicates: false if no duplicates are found.";

const RESPONSE_SCHEMA = {
  type: "object",
  properties: {
    has_duplicates: { type: "boolean" },
    duplicate_groups: {
      type: "array",
      items: {
        type: "object",
        properties: {
          keep_id: { type: "string" },
          delete_ids: { type: "array", items: { type: "string" } },
          reason: { type: "string" },
        },
        required: ["keep_id", "delete_ids", "reason"],
      },
    },
  },
  required: ["has_duplicates", "duplicate_groups"],
};

async function callGeminiJson(prompt: string): Promise<DedupResponse | null> {
  const body = {
    system_instruction: { parts: [{ text: SYSTEM_PROMPT }] },
    contents: [{ role: "user", parts: [{ text: prompt }] }],
    generationConfig: {
      maxOutputTokens: 4096,
      temperature: 0.1,
      responseMimeType: "application/json",
      responseSchema: RESPONSE_SCHEMA,
    },
  };
  try {
    const resp = await api.post<GeminiJsonResponse>(GEMINI_PATH, body);
    const text = resp?.candidates?.[0]?.content?.parts?.[0]?.text;
    if (!text) return null;
    return JSON.parse(text) as DedupResponse;
  } catch (err) {
    console.warn("[TaskDedup] Gemini call failed:", err);
    return null;
  }
}

async function runOnce(): Promise<void> {
  lastRunAt = Date.now();
  let tasks: RustStagedTask[] = [];
  try {
    tasks = await invoke<RustStagedTask[]>("get_staged_tasks", { limit: 200 });
  } catch (err) {
    console.warn("[TaskDedup] failed to fetch staged tasks:", err);
    return;
  }
  // `get_staged_tasks` already filters out deleted — still defensive here.
  tasks = tasks.filter((t) => !t.deleted && !t.completed);
  if (tasks.length < MINIMUM_TASK_COUNT) {
    console.info(
      `[TaskDedup] only ${tasks.length} staged tasks — skipping (min ${MINIMUM_TASK_COUNT})`,
    );
    return;
  }
  console.info(`[TaskDedup] analyzing ${tasks.length} staged tasks`);

  const result = await callGeminiJson(buildPrompt(tasks));
  if (!result || !result.has_duplicates || !result.duplicate_groups.length) {
    console.info("[TaskDedup] no duplicates found");
    return;
  }

  const validIds = new Set(tasks.map((t) => t.id));
  const lookup = new Map(tasks.map((t) => [t.id, t]));
  let deleted = 0;

  for (const group of result.duplicate_groups) {
    if (!validIds.has(group.keep_id)) continue;
    const toDelete = group.delete_ids.filter(
      (id) => validIds.has(id) && id !== group.keep_id,
    );
    if (toDelete.length === 0) continue;

    try {
      await invoke("insert_dedup_log", {
        input: {
          kept_id: group.keep_id,
          deleted_ids: toDelete,
          reason: group.reason,
        },
      });
    } catch (err) {
      console.warn("[TaskDedup] dedup log failed:", err);
    }

    for (const id of toDelete) {
      const task = lookup.get(id);
      try {
        await invoke("delete_staged_task", { id, hard: true });
        deleted++;
      } catch (err) {
        console.warn(`[TaskDedup] local delete failed (${id}):`, err);
        continue;
      }
      // Best-effort mirror to backend.
      if (task?.backend_id) {
        try {
          await api.delete(`/v1/staged-tasks/${task.backend_id}`);
        } catch (err) {
          console.warn(`[TaskDedup] backend delete failed (${task.backend_id}):`, err);
        }
      }
    }
  }

  console.info(`[TaskDedup] hard-deleted ${deleted} duplicates`);
}

function schedule(delayMs: number): void {
  if (timerId !== null) {
    clearTimeout(timerId);
    timerId = null;
  }
  timerId = setTimeout(async () => {
    if (!running) return;
    const sinceLast = Date.now() - lastRunAt;
    if (lastRunAt > 0 && sinceLast < COOLDOWN_MS) {
      schedule(COOLDOWN_MS - sinceLast);
      return;
    }
    try {
      await runOnce();
    } catch (err) {
      console.warn("[TaskDedup] run failed:", err);
    }
    if (running) schedule(INTERVAL_MS);
  }, delayMs);
}

/** Start the periodic dedup service. Idempotent. */
export function startTaskDeduplication(): void {
  if (running) return;
  running = true;
  console.info("[TaskDedup] service started");
  schedule(STARTUP_DELAY_MS);
}

/** Stop the periodic dedup service. */
export function stopTaskDeduplication(): void {
  if (!running) return;
  running = false;
  if (timerId !== null) {
    clearTimeout(timerId);
    timerId = null;
  }
  console.info("[TaskDedup] service stopped");
}
