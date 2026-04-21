import { useMemo, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  Check,
  Copy,
  Mic,
  MoreHorizontal,
  Search,
  Trash2,
  X,
} from "lucide-react";
import {
  useWhisprStore,
  type WhisprEntry,
} from "@/stores/whisprStore";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const MS_PER_DAY = 86_400_000;

function countThisWeek(entries: WhisprEntry[]): number {
  const cutoff = Date.now() - 7 * MS_PER_DAY;
  let n = 0;
  for (const e of entries) {
    const t = Date.parse(e.createdAt);
    if (!Number.isNaN(t) && t >= cutoff) n += 1;
  }
  return n;
}

function formatRelative(iso: string): string {
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "";
  const diff = Date.now() - t;
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  const d = new Date(t);
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(ms: number | undefined): string | null {
  if (ms == null || ms <= 0) return null;
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const mins = Math.floor(s / 60);
  const rem = Math.round(s - mins * 60);
  return `${mins}m ${rem}s`;
}

export function WhisprPage() {
  const entries = useWhisprStore((s) => s.entries);
  const remove = useWhisprStore((s) => s.remove);
  const clear = useWhisprStore((s) => s.clear);

  const [query, setQuery] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter((e) => e.text.toLowerCase().includes(q));
  }, [entries, query]);

  const thisWeek = useMemo(() => countThisWeek(entries), [entries]);

  const subtitle =
    entries.length === 0
      ? "Your dictation history appears here."
      : thisWeek > 0
        ? `${entries.length} transcripts · ${thisWeek} this week`
        : `${entries.length} transcripts`;

  const handleCopy = async (entry: WhisprEntry) => {
    try {
      await invoke("copy_to_clipboard", { text: entry.text });
      setCopiedId(entry.id);
      window.setTimeout(() => {
        setCopiedId((cur) => (cur === entry.id ? null : cur));
      }, 1400);
    } catch (err) {
      console.warn("[Whispr] copy failed:", err);
    }
  };

  return (
    <div className="memories-page">
      <PageHeader
        title="Whispr"
        subtitle={subtitle}
        actions={
          entries.length > 0 ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" aria-label="More">
                  <MoreHorizontal size={16} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={() => setConfirmClear(true)}
                  variant="destructive"
                >
                  <Trash2 size={14} />
                  Clear history
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : null
        }
      >
        {entries.length > 0 && (
          <div className="memories-search">
            <Search className="memories-search-icon" />
            <input
              className="memories-search-input"
              placeholder="Search transcripts"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            {query.length > 0 && (
              <button
                type="button"
                className="memories-search-clear"
                onClick={() => setQuery("")}
                aria-label="Clear search"
              >
                <X className="memories-search-clear-icon" />
              </button>
            )}
          </div>
        )}
      </PageHeader>

      <div className="memories-content">
        {entries.length === 0 ? (
          <div className="page-empty flex flex-col items-center gap-3 py-24 text-muted-foreground">
            <div className="flex size-12 items-center justify-center rounded-full bg-muted">
              <Mic size={20} className="opacity-70" />
            </div>
            <span className="text-sm font-medium text-foreground">
              Nothing to show yet
            </span>
            <span className="max-w-xs text-center text-xs">
              Hold <kbd className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">AltGr</kbd> anywhere and speak — the transcript will appear here and on your clipboard.
            </span>
          </div>
        ) : filtered.length === 0 ? (
          <div className="page-empty">No transcripts match your search.</div>
        ) : (
          <div className="flex flex-col gap-2">
            {filtered.map((entry) => {
              const copied = copiedId === entry.id;
              const duration = formatDuration(entry.durationMs);
              return (
                <div
                  key={entry.id}
                  className="group flex items-start gap-3 rounded-lg border border-border/50 bg-card/30 p-3 transition-colors hover:border-border/80 hover:bg-card/50"
                >
                  <div className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                    <Mic size={13} />
                  </div>
                  <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                    <p className="text-sm leading-relaxed text-foreground/90">
                      {entry.text}
                    </p>
                    <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                      <span>{formatRelative(entry.createdAt)}</span>
                      {duration && (
                        <>
                          <span className="opacity-50">·</span>
                          <span>{duration}</span>
                        </>
                      )}
                      {entry.autoPasted && (
                        <>
                          <span className="opacity-50">·</span>
                          <span>auto-pasted</span>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleCopy(entry)}
                      className="h-7 gap-1.5 text-xs"
                    >
                      {copied ? (
                        <>
                          <Check size={13} /> Copied
                        </>
                      ) : (
                        <>
                          <Copy size={13} /> Copy
                        </>
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => remove(entry.id)}
                      aria-label="Delete"
                      className="size-7 text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 size={13} />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <Dialog open={confirmClear} onOpenChange={setConfirmClear}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Clear Whispr history?</DialogTitle>
            <DialogDescription>
              This removes every transcript from your local history. This
              action can't be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmClear(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => {
                clear();
                setConfirmClear(false);
              }}
            >
              Clear
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
