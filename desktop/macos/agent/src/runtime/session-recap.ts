import type { AgentStore } from "./types.js";

/**
 * What a session did before, for an adapter that no longer remembers it.
 *
 * A session's transcript lives inside the adapter process. pi-mono reports
 * `resumeFidelity: "none"`, so when its binding is replaced — a restart, a
 * recycled worker, a changed MCP set — the next run opens a blank adapter
 * session and the follow-up arrives with no antecedent: "now search it for
 * macOS Tahoe" with nothing to attach "it" to.
 *
 * The runs table has already recorded every prompt and every final answer, so
 * the transcript is not actually lost, only unread. This rebuilds a bounded
 * summary of it and hands it to the fresh binding.
 */

const DEFAULT_MAX_RUNS = 12;
const DEFAULT_MAX_CHARS = 6_000;
const MAX_PROMPT_CHARS = 400;
const MAX_ANSWER_CHARS = 600;

/** Runs that produced something a later turn can refer back to. */
const RECAPPED_STATUSES = ["succeeded", "failed", "cancelled", "timed_out"] as const;

export interface SessionRecapInput {
  sessionId: string;
  /** The run being prepared, excluded from its own recap. */
  currentRunId: string;
  /** The binding about to execute. A recap is only needed when it did not run the prior turns. */
  currentBindingId: string | null;
  maxRuns?: number;
  maxChars?: number;
}

export interface SessionRecap {
  text: string;
  runCount: number;
  /** The binding that held the transcript this recap replaces, when one is on record. */
  priorBindingId: string | null;
  truncated: boolean;
}

interface RecapRow {
  runId: string;
  prompt: string;
  answer: string;
  status: string;
  bindingId: string | null;
}

export function buildSessionRecap(store: AgentStore, input: SessionRecapInput): SessionRecap | undefined {
  const maxRuns = Math.max(1, Math.min(input.maxRuns ?? DEFAULT_MAX_RUNS, 50));
  const rows = store.allRows(
    `SELECT r.run_id, r.input_json, r.final_text, r.status,
            (SELECT a.binding_id FROM run_attempts a
              WHERE a.run_id = r.run_id AND a.binding_id IS NOT NULL
              ORDER BY a.attempt_no DESC LIMIT 1) AS binding_id
       FROM runs r
      WHERE r.session_id = ?
        AND r.run_id != ?
        AND r.status IN (${RECAPPED_STATUSES.map(() => "?").join(", ")})
      ORDER BY r.created_at_ms DESC
      LIMIT ?`,
    [input.sessionId, input.currentRunId, ...RECAPPED_STATUSES, maxRuns],
  );
  if (rows.length === 0) return undefined;

  const priorBindingId = firstBindingId(rows);
  // The adapter still holds this transcript itself; replaying it would only
  // duplicate what the model can already see.
  if (priorBindingId !== null && priorBindingId === input.currentBindingId) return undefined;

  const entries: RecapRow[] = [];
  for (const row of rows) {
    const prompt = clamp(promptOf(row.input_json), MAX_PROMPT_CHARS);
    if (!prompt) continue;
    entries.push({
      runId: String(row.run_id ?? ""),
      prompt,
      answer: clamp(typeof row.final_text === "string" ? row.final_text : "", MAX_ANSWER_CHARS),
      status: String(row.status ?? ""),
      bindingId: row.binding_id === null || row.binding_id === undefined ? null : String(row.binding_id),
    });
  }
  if (entries.length === 0) return undefined;

  entries.reverse();
  return render(entries, Math.max(500, input.maxChars ?? DEFAULT_MAX_CHARS), priorBindingId);
}

function render(entries: RecapRow[], maxChars: number, priorBindingId: string | null): SessionRecap {
  const lines: string[] = [];
  let used = 0;
  let kept = 0;
  // Oldest first is the reading order, but the newest turns are the ones a
  // follow-up refers to, so the budget is spent from the end backwards.
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const block = renderEntry(entries[index]);
    if (used + block.length > maxChars && kept > 0) break;
    lines.unshift(block);
    used += block.length;
    kept += 1;
  }
  return {
    text: `${HEADER}\n\n${lines.join("\n\n")}`,
    runCount: kept,
    priorBindingId,
    truncated: kept < entries.length,
  };
}

const HEADER = [
  "# Earlier In This Session",
  "",
  "You are continuing work you already started. The process holding the original",
  "conversation restarted, so what follows is a summary of it rather than the",
  "transcript itself. Treat it as your own memory: pronouns and references in the",
  "user's next message point at the app, window, or task named here. If the",
  "summary does not say where something ended up, look before acting.",
].join("\n");

function renderEntry(entry: RecapRow): string {
  const outcome = entry.status === "succeeded"
    ? entry.answer || "(no final answer recorded)"
    : `(${entry.status}) ${entry.answer}`.trim();
  return `User: ${entry.prompt}\nYou: ${outcome}`;
}

function firstBindingId(rows: readonly Record<string, unknown>[]): string | null {
  for (const row of rows) {
    if (row.binding_id !== null && row.binding_id !== undefined) return String(row.binding_id);
  }
  return null;
}

function promptOf(value: unknown): string {
  if (typeof value !== "string") return "";
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return "";
    const prompt = (parsed as Record<string, unknown>).prompt;
    return typeof prompt === "string" ? userMessageOf(prompt) : "";
  } catch {
    return "";
  }
}

const USER_MESSAGE_MARKER = "\n# User Message\n";
/** `ChatPrompts` prepends an authoritative clock ahead of what the user typed. */
const CLOCK_PREAMBLE = /^# Current Time\n[^\n]*\n\n/;

/**
 * What the user actually said, out of a prompt that reached storage with context
 * already prepended. Recapping the wrapper instead would spend the whole budget
 * on a timestamp and clip off the sentence a follow-up refers to.
 */
function userMessageOf(prompt: string): string {
  const marked = prompt.lastIndexOf(USER_MESSAGE_MARKER);
  if (marked !== -1) return prompt.slice(marked + USER_MESSAGE_MARKER.length).trim();
  return prompt.replace(CLOCK_PREAMBLE, "").trim();
}

function clamp(value: string, maxChars: number): string {
  const collapsed = value.replace(/\s+/g, " ").trim();
  return collapsed.length <= maxChars ? collapsed : `${collapsed.slice(0, maxChars - 1)}…`;
}
