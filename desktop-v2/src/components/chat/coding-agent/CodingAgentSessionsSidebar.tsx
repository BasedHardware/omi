/**
 * CodingAgentSessionsSidebar — left rail for the coding-agent (Code mode).
 *
 * Shows a "Recents" stripe of the 5 most-recently modified sessions, then the
 * rest grouped by project folder basename with time-bucket sub-headers (mirroring
 * ChatSessionsSidebar's pattern).
 *
 * Selection triggers `useCodingAgent.startSession(cwd, "", model, filePath)` so
 * the sidecar restores the JSONL session.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { formatDistanceToNow, isToday, isYesterday } from "date-fns";
import { Check, FolderOpen, Pencil, Plus, Trash2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  useCodingAgentSessionsStore,
  type CodingAgentSessionMeta,
} from "./codingAgentSessionsStore";
import { useCodingAgent } from "@/hooks/useCodingAgent";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatRelativeDate(ms: number): string {
  const d = new Date(ms);
  if (isToday(d)) return "Today";
  if (isYesterday(d)) return "Yesterday";
  return formatDistanceToNow(d, { addSuffix: true });
}

interface TimeBucket {
  label: string;
  sessions: CodingAgentSessionMeta[];
}

function bucketByTime(sessions: CodingAgentSessionMeta[]): TimeBucket[] {
  const today: CodingAgentSessionMeta[] = [];
  const yesterday: CodingAgentSessionMeta[] = [];
  const week: CodingAgentSessionMeta[] = [];
  const older: CodingAgentSessionMeta[] = [];
  const now = Date.now();
  const sevenDays = 7 * 24 * 60 * 60 * 1000;

  for (const s of sessions) {
    const ts = s.modifiedAt;
    if (isToday(new Date(ts))) today.push(s);
    else if (isYesterday(new Date(ts))) yesterday.push(s);
    else if (now - ts < sevenDays) week.push(s);
    else older.push(s);
  }

  const out: TimeBucket[] = [];
  if (today.length) out.push({ label: "Today", sessions: today });
  if (yesterday.length) out.push({ label: "Yesterday", sessions: yesterday });
  if (week.length) out.push({ label: "This week", sessions: week });
  if (older.length) out.push({ label: "Older", sessions: older });
  return out;
}

/** Returns the basename of a path (last segment). */
function folderBasename(cwd: string): string {
  return cwd.split("/").filter(Boolean).pop() ?? cwd;
}

// ---------------------------------------------------------------------------
// Session row
// ---------------------------------------------------------------------------

function SessionRow({
  session,
  isSelected,
  onSelect,
  onDelete,
  onRename,
}: {
  session: CodingAgentSessionMeta;
  isSelected: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onRename: (name: string) => void;
}) {
  const [isHovering, setHovering] = useState(false);
  const [isEditing, setEditing] = useState(false);
  const [draft, setDraft] = useState(session.name ?? "");

  const displayName = session.name || formatRelativeDate(session.modifiedAt);

  const startEdit = () => {
    setDraft(session.name ?? "");
    setEditing(true);
  };

  const commit = () => {
    const t = draft.trim();
    onRename(t); // allow empty to clear the name
    setEditing(false);
  };

  const cancel = () => {
    setEditing(false);
    setDraft(session.name ?? "");
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      onClick={() => !isEditing && onSelect()}
      onKeyDown={(e) => {
        if (!isEditing && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          onSelect();
        }
      }}
      className={cn(
        "chat-session-row",
        isSelected && "chat-session-row--selected",
      )}
    >
      <div className="chat-session-row__main">
        {isEditing ? (
          <input
            autoFocus
            className="chat-session-row__input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                commit();
              } else if (e.key === "Escape") {
                e.preventDefault();
                cancel();
              }
            }}
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span className="chat-session-row__title" title={session.name ?? session.cwd}>
            {displayName}
          </span>
        )}
        {!isEditing && (
          <span className="chat-session-row__date">
            {session.messageCount} {session.messageCount === 1 ? "msg" : "msgs"}
          </span>
        )}
      </div>

      {isEditing ? (
        <div
          className="chat-session-row__actions"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            className="chat-session-row__action"
            aria-label="Save"
            onClick={commit}
          >
            <Check className="size-3" />
          </button>
          <button
            type="button"
            className="chat-session-row__action"
            aria-label="Cancel"
            onClick={cancel}
          >
            <X className="size-3" />
          </button>
        </div>
      ) : (
        isHovering && (
          <div className="chat-session-row__actions">
            <button
              type="button"
              className="chat-session-row__action"
              aria-label="Rename session"
              onClick={(e) => {
                e.stopPropagation();
                startEdit();
              }}
            >
              <Pencil className="size-3" />
            </button>
            <button
              type="button"
              className="chat-session-row__action chat-session-row__action--danger"
              aria-label="Delete session"
              onClick={(e) => {
                e.stopPropagation();
                if (window.confirm("Delete this session? This cannot be undone.")) {
                  onDelete();
                }
              }}
            >
              <Trash2 className="size-3" />
            </button>
          </div>
        )
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

const RECENT_COUNT = 5;
const MODEL_STORAGE_KEY = "coding-agent:model";

export function CodingAgentSessionsSidebar() {
  const sessions = useCodingAgentSessionsStore((s) => s.sessions);
  const currentFilePath = useCodingAgentSessionsStore((s) => s.currentFilePath);
  const refresh = useCodingAgentSessionsStore((s) => s.refresh);
  const selectSession = useCodingAgentSessionsStore((s) => s.selectSession);
  const rename = useCodingAgentSessionsStore((s) => s.rename);
  const remove = useCodingAgentSessionsStore((s) => s.remove);

  const { pickFolder, startSession } = useCodingAgent();

  // Refresh on mount so the list is current after the app re-opens.
  useEffect(() => {
    void refresh();
  }, [refresh]);

  const model =
    typeof window !== "undefined"
      ? (localStorage.getItem(MODEL_STORAGE_KEY) ?? undefined)
      : undefined;

  const handleSelectSession = useCallback(
    async (meta: CodingAgentSessionMeta) => {
      // Update both pointers — the CodingAgentSession reads currentCwd from
      // the store to render its folder pill.
      selectSession(meta.filePath, meta.cwd);
      try {
        await startSession(meta.cwd, "", model, meta.filePath);
      } catch (err) {
        console.error("[CodingAgentSessionsSidebar] startSession failed:", err);
      }
    },
    [selectSession, startSession, model],
  );

  const handleNewSession = useCallback(async () => {
    const folder = await pickFolder();
    if (!folder) return;
    // Clear the active session pointer but pin the new folder so the user
    // can start typing immediately in the main panel.
    selectSession(null, folder);
  }, [selectSession, pickFolder]);

  // ---------------------------------------------------------------------------
  // Compute "Recents" stripe + grouped remainder
  // ---------------------------------------------------------------------------

  const { recents, grouped } = useMemo(() => {
    const sorted = [...sessions].sort((a, b) => b.modifiedAt - a.modifiedAt);

    // Recents: top 5 by modifiedAt.
    const recentSet = new Set(sorted.slice(0, RECENT_COUNT).map((s) => s.filePath));
    const recentItems = sorted.slice(0, RECENT_COUNT);

    // Remainder: sessions not in the recents stripe, grouped by project.
    const rest = sorted.filter((s) => !recentSet.has(s.filePath));

    // Group by cwd (project folder).
    const projectMap = new Map<string, CodingAgentSessionMeta[]>();
    for (const s of rest) {
      const key = s.cwd;
      const bucket = projectMap.get(key) ?? [];
      bucket.push(s);
      projectMap.set(key, bucket);
    }

    const projectGroups = Array.from(projectMap.entries()).map(([cwd, items]) => ({
      cwd,
      name: folderBasename(cwd),
      buckets: bucketByTime(items),
    }));

    return { recents: recentItems, grouped: projectGroups };
  }, [sessions]);

  const onlyOneProject = grouped.length <= 1;

  return (
    <aside className="chat-sessions-sidebar">
      <div className="chat-sessions-sidebar__header">
        <button
          type="button"
          onClick={() => void handleNewSession()}
          className="chat-sessions-sidebar__new"
        >
          <Plus className="size-3.5" />
          <span>New session</span>
        </button>
      </div>

      <div className="chat-sessions-sidebar__list">
        {sessions.length === 0 ? (
          <div className="chat-sessions-sidebar__empty">
            <p>No sessions yet</p>
            <span>Start a coding session to see it here.</span>
          </div>
        ) : (
          <>
            {/* Recents stripe */}
            {recents.length > 0 && (
              <div className="chat-sessions-sidebar__group">
                <div className="chat-sessions-sidebar__group-label">Recents</div>
                {recents.map((s) => (
                  <SessionRow
                    key={s.filePath}
                    session={s}
                    isSelected={s.filePath === currentFilePath}
                    onSelect={() => void handleSelectSession(s)}
                    onDelete={() => void remove(s.filePath)}
                    onRename={(name) => void rename(s.filePath, name)}
                  />
                ))}
              </div>
            )}

            {/* Project groups */}
            {grouped.map((project) => (
              <div key={project.cwd} className="chat-sessions-sidebar__group">
                {/* Only show project header when more than one project exists */}
                {!onlyOneProject && (
                  <div
                    className="flex items-center gap-1.5 chat-sessions-sidebar__group-label"
                    title={project.cwd}
                  >
                    <FolderOpen className="size-3 shrink-0" />
                    <span className="truncate">{project.name}</span>
                  </div>
                )}
                {project.buckets.map((bucket) => (
                  <div key={bucket.label}>
                    {!onlyOneProject && (
                      <div className="chat-sessions-sidebar__group-label pl-4 text-muted-foreground/60">
                        {bucket.label}
                      </div>
                    )}
                    {onlyOneProject && (
                      <div className="chat-sessions-sidebar__group-label">
                        {bucket.label}
                      </div>
                    )}
                    {bucket.sessions.map((s) => (
                      <SessionRow
                        key={s.filePath}
                        session={s}
                        isSelected={s.filePath === currentFilePath}
                        onSelect={() => void handleSelectSession(s)}
                        onDelete={() => void remove(s.filePath)}
                        onRename={(name) => void rename(s.filePath, name)}
                      />
                    ))}
                  </div>
                ))}
              </div>
            ))}
          </>
        )}
      </div>
    </aside>
  );
}
