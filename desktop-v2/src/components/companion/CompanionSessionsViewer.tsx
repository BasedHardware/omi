/**
 * CompanionSessionsViewer — debug-mode list of recent Companion Q&A sessions
 * with expandable detail rows.
 *
 * Lives in Settings → Companion → Recent Sessions. Reads from the SQLite
 * `companion_sessions` table (extended in migration V4 with telemetry columns)
 * via `plugin:screen-capture|get_recent_companion_sessions`. Each row shows
 * one interaction; click to expand for the full Gemini JSON, chain steps with
 * grounding methods, and screenshot reference.
 *
 * Intentionally minimal: no search, no filters, no charts. The point is to
 * accelerate the prompt-tuning loop ("I just held PTT, why did it pick Mode A?")
 * not to be a product surface. If we ever want a user-facing history page,
 * promote this to its own route.
 */
import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Button } from "@/components/ui/button";
import { Trash2, RefreshCw, ChevronDown, ChevronRight } from "lucide-react";

interface CompanionSessionRow {
  id: number;
  timestamp: number;
  transcript: string;
  answer: string;
  points_json: string;
  screenshot_id: number | null;
  display_id: number;
  // V4 telemetry — all nullable for backward compatibility with older rows.
  mode: "single" | "chain" | null;
  steps_json: string | null;
  gemini_raw_json: string | null;
  active_app: string | null;
  active_bundle_id: string | null;
  duration_ms: number | null;
  chain_completed: boolean | null;
  chain_steps_completed: number | null;
  grounding_methods_json: string | null;
  error: string | null;
}

const ROW_LIMIT = 50;

export function CompanionSessionsViewer() {
  const [rows, setRows] = useState<CompanionSessionRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const fetched = await invoke<CompanionSessionRow[]>(
        "plugin:screen-capture|get_recent_companion_sessions",
        { limit: ROW_LIMIT },
      );
      setRows(fetched);
    } catch (e) {
      console.warn("[CompanionSessionsViewer] load failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const toggleRow = useCallback((id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const onDelete = useCallback(
    async (id: number) => {
      try {
        await invoke("plugin:screen-capture|delete_companion_session", { id });
        setRows((prev) => prev.filter((r) => r.id !== id));
      } catch (e) {
        console.warn("[CompanionSessionsViewer] delete failed:", e);
      }
    },
    [],
  );

  const onDeleteAll = useCallback(async () => {
    // Delete each visible row in turn. We don't expose a wholesale "truncate
    // companion_sessions" command — keeping bulk operations explicit avoids
    // accidental data loss.
    for (const r of rows) {
      try {
        await invoke("plugin:screen-capture|delete_companion_session", { id: r.id });
      } catch (e) {
        console.warn("[CompanionSessionsViewer] delete failed:", e);
      }
    }
    void refresh();
  }, [rows, refresh]);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground text-xs">
          Last {ROW_LIMIT} interactions. Click a row to inspect the raw Gemini response,
          chain steps, grounding methods, and outcome.
        </p>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void refresh()}
            disabled={loading}
            aria-label="Refresh"
          >
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} aria-hidden />
            Refresh
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void onDeleteAll()}
            disabled={loading || rows.length === 0}
            aria-label="Delete all"
          >
            <Trash2 className="size-3.5" aria-hidden />
            Delete all
          </Button>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="text-muted-foreground rounded-md border border-dashed border-border px-3 py-6 text-center text-xs">
          No sessions yet — hold the Companion PTT key and ask a question to populate this log.
        </div>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {rows.map((r) => (
            <SessionRow
              key={r.id}
              row={r}
              expanded={expanded.has(r.id)}
              onToggle={() => toggleRow(r.id)}
              onDelete={() => void onDelete(r.id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function SessionRow({
  row,
  expanded,
  onToggle,
  onDelete,
}: {
  row: CompanionSessionRow;
  expanded: boolean;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const ago = formatTimeAgo(row.timestamp);
  const modeColor =
    row.mode === "chain"
      ? "bg-blue-500/15 text-blue-300 border-blue-500/30"
      : row.mode === "single"
        ? "bg-zinc-500/15 text-zinc-300 border-zinc-500/30"
        : "bg-zinc-700/15 text-zinc-500 border-zinc-700/30";
  // Chain rows have a richer completion picture than a single icon. We
  // distinguish in-progress (chain_completed is null AND no error) from
  // abandoned (chain_completed is false) from done (true).
  const chainStatus = computeChainStatus(row);
  const completionIcon =
    row.error
      ? "✗"
      : row.mode === "chain"
        ? chainStatus === "done"
          ? "✓"
          : chainStatus === "abandoned"
            ? "·"
            : "…"
        : "—";

  return (
    <li className="rounded-md border border-border bg-card/50">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left hover:bg-card/80"
      >
        {expanded ? (
          <ChevronDown className="size-3.5 text-muted-foreground shrink-0" aria-hidden />
        ) : (
          <ChevronRight className="size-3.5 text-muted-foreground shrink-0" aria-hidden />
        )}
        <span className="text-muted-foreground w-12 shrink-0 text-[11px] tabular-nums">{ago}</span>
        <span
          className={`shrink-0 rounded-sm border px-1.5 py-0.5 text-[10px] font-medium ${modeColor}`}
        >
          {row.mode ?? "?"}
        </span>
        {row.active_app ? (
          <span className="text-muted-foreground shrink-0 truncate max-w-[120px] text-[11px]">
            {row.active_app}
          </span>
        ) : null}
        <span className="text-foreground/80 grow truncate text-xs">
          {row.answer || "(no answer)"}
        </span>
        <span className="text-muted-foreground shrink-0 text-xs tabular-nums w-4 text-right">
          {completionIcon}
        </span>
      </button>

      {expanded ? (
        <div className="border-t border-border px-3 py-2.5 text-xs">
          <DetailGrid row={row} />
          <div className="mt-2.5 flex justify-end">
            <Button size="sm" variant="ghost" onClick={onDelete}>
              <Trash2 className="size-3.5" aria-hidden />
              Delete
            </Button>
          </div>
        </div>
      ) : null}
    </li>
  );
}

function DetailGrid({ row }: { row: CompanionSessionRow }) {
  const steps = parseJson<Array<{ instruction: string; target_label: string }>>(row.steps_json);
  const grounding = parseJson<string[]>(row.grounding_methods_json);
  const rawPretty = row.gemini_raw_json
    ? prettyJson(row.gemini_raw_json)
    : null;
  const chainStatus = computeChainStatus(row);
  const chainStatusLabel: Record<ReturnType<typeof computeChainStatus>, string> = {
    "n/a": "—",
    "in-progress": "in progress",
    abandoned: "abandoned",
    done: "completed",
  };

  return (
    <div className="flex flex-col gap-2.5">
      <Field label="Answer" value={row.answer} />
      {row.error ? <Field label="Error" value={row.error} accent="destructive" /> : null}
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
        <Meta label="Mode" value={row.mode ?? "—"} />
        <Meta
          label="Duration"
          value={row.duration_ms ? `${(row.duration_ms / 1000).toFixed(1)}s` : "—"}
        />
        <Meta label="Active app" value={row.active_app ?? "—"} />
        <Meta label="Bundle id" value={row.active_bundle_id ?? "—"} />
        <Meta label="Display id" value={String(row.display_id)} />
        <Meta label="Screenshot id" value={row.screenshot_id != null ? String(row.screenshot_id) : "—"} />
        {row.mode === "chain" ? (
          <>
            <Meta
              label="Chain progress"
              value={
                steps
                  ? `${row.chain_steps_completed ?? 0} / ${steps.length}`
                  : "—"
              }
            />
            <Meta label="Status" value={chainStatusLabel[chainStatus]} />
          </>
        ) : null}
      </div>

      {steps && steps.length > 0 ? (
        <div>
          <p className="text-muted-foreground mb-1 text-[10px] uppercase tracking-wide">Steps</p>
          <ol className="flex flex-col gap-1 text-[11px]">
            {steps.map((s, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="text-muted-foreground tabular-nums w-5 shrink-0">{i + 1}.</span>
                <span className="grow">
                  <span className="text-foreground/90">{s.instruction}</span>{" "}
                  <span className="text-muted-foreground">
                    → <code className="font-mono">{s.target_label}</code>
                  </span>
                </span>
                {grounding && grounding[i] ? (
                  <span
                    className={`shrink-0 rounded-sm border px-1 py-0.5 text-[9px] uppercase tabular-nums ${groundingColor(grounding[i])}`}
                  >
                    {grounding[i]}
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {rawPretty ? (
        <details className="rounded-sm border border-border/60 bg-background/40">
          <summary className="cursor-pointer px-2 py-1 text-[10px] uppercase tracking-wide text-muted-foreground">
            Raw Gemini response
          </summary>
          <pre className="overflow-x-auto px-2 py-1 text-[10px] font-mono leading-tight">
            {rawPretty}
          </pre>
        </details>
      ) : null}
    </div>
  );
}

function Field({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "destructive";
}) {
  return (
    <div>
      <p className="text-muted-foreground mb-0.5 text-[10px] uppercase tracking-wide">{label}</p>
      <p
        className={`whitespace-pre-wrap text-xs ${accent === "destructive" ? "text-destructive" : "text-foreground/90"}`}
      >
        {value}
      </p>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-muted-foreground">{label}:</span>
      <span className="text-foreground/80 truncate">{value}</span>
    </div>
  );
}

function groundingColor(method: string): string {
  switch (method) {
    case "ax":
      return "bg-emerald-500/15 text-emerald-300 border-emerald-500/30";
    case "ocr":
      return "bg-amber-500/15 text-amber-300 border-amber-500/30";
    case "gemini":
      return "bg-blue-500/15 text-blue-300 border-blue-500/30";
    default:
      return "bg-zinc-500/15 text-zinc-400 border-zinc-500/30";
  }
}

function parseJson<T>(s: string | null): T | null {
  if (!s) return null;
  try {
    return JSON.parse(s) as T;
  } catch {
    return null;
  }
}

function prettyJson(s: string): string {
  try {
    return JSON.stringify(JSON.parse(s), null, 2);
  } catch {
    return s;
  }
}

function formatTimeAgo(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 60_000) return `${Math.max(1, Math.round(diff / 1000))}s`;
  if (diff < 3_600_000) return `${Math.round(diff / 60_000)}m`;
  if (diff < 86_400_000) return `${Math.round(diff / 3_600_000)}h`;
  return `${Math.round(diff / 86_400_000)}d`;
}

/** Bucket a row into one of four chain states based on the telemetry the
 *  post-chain UPDATE writes:
 *   - "n/a"         → not a chain row (single-shot answer)
 *   - "in-progress" → chain saved at start, no UPDATE yet (still running OR
 *                     never advanced past planning)
 *   - "abandoned"   → UPDATE wrote chain_completed=false (Esc / new PTT /
 *                     grounding failure)
 *   - "done"        → UPDATE wrote chain_completed=true (all steps clicked)
 */
function computeChainStatus(
  row: CompanionSessionRow,
): "n/a" | "in-progress" | "abandoned" | "done" {
  if (row.mode !== "chain") return "n/a";
  if (row.chain_completed === true) return "done";
  if (row.chain_completed === false) return "abandoned";
  return "in-progress";
}
