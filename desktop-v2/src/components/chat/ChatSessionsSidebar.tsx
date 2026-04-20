/**
 * ChatSessionsSidebar — left sub-sidebar inside ChatPage.
 *
 * Lists prior chat sessions with titles and relative dates. The current
 * session is highlighted. Hover reveals a delete affordance.
 */

import { useMemo, useState } from "react";
import { formatDistanceToNow, isToday, isYesterday } from "date-fns";
import { Check, Pencil, Plus, Trash2, X } from "lucide-react";
import type { ChatSession } from "@/stores/chatStore";
import { useChatStore } from "@/stores/chatStore";
import { cn } from "@/lib/utils";

function formatRelativeDate(iso: string): string {
  const d = new Date(iso);
  if (isToday(d)) return "Today";
  if (isYesterday(d)) return "Yesterday";
  return formatDistanceToNow(d, { addSuffix: true });
}

interface GroupedSessions {
  label: string;
  sessions: ChatSession[];
}

function groupSessions(sessions: ChatSession[]): GroupedSessions[] {
  if (sessions.length === 0) return [];
  const today: ChatSession[] = [];
  const yesterday: ChatSession[] = [];
  const week: ChatSession[] = [];
  const older: ChatSession[] = [];
  const now = Date.now();
  const sevenDays = 7 * 24 * 60 * 60 * 1000;

  for (const s of sessions) {
    const ts = new Date(s.updatedAt).getTime();
    if (isToday(new Date(ts))) today.push(s);
    else if (isYesterday(new Date(ts))) yesterday.push(s);
    else if (now - ts < sevenDays) week.push(s);
    else older.push(s);
  }

  const groups: GroupedSessions[] = [];
  if (today.length) groups.push({ label: "Today", sessions: today });
  if (yesterday.length) groups.push({ label: "Yesterday", sessions: yesterday });
  if (week.length) groups.push({ label: "This week", sessions: week });
  if (older.length) groups.push({ label: "Older", sessions: older });
  return groups;
}

function SessionRow({
  session,
  isSelected,
  onSelect,
  onDelete,
  onRename,
}: {
  session: ChatSession;
  isSelected: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onRename: (title: string) => void;
}) {
  const [isHovering, setHovering] = useState(false);
  const [isEditing, setEditing] = useState(false);
  const [draft, setDraft] = useState(session.title);

  const startEdit = () => {
    setDraft(session.title);
    setEditing(true);
  };

  const commit = () => {
    const t = draft.trim();
    if (t && t !== session.title) {
      onRename(t);
    }
    setEditing(false);
  };

  const cancel = () => {
    setEditing(false);
    setDraft(session.title);
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
          <span className="chat-session-row__title" title={session.title}>
            {session.title}
          </span>
        )}
        {!isEditing && session.preview && (
          <span className="chat-session-row__preview">{session.preview}</span>
        )}
        {!isEditing && (
          <span className="chat-session-row__date">
            {formatRelativeDate(session.updatedAt)}
          </span>
        )}
      </div>
      {isEditing ? (
        <div className="chat-session-row__actions" onClick={(e) => e.stopPropagation()}>
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
              aria-label="Rename chat"
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
              aria-label="Delete chat"
              onClick={(e) => {
                e.stopPropagation();
                if (window.confirm("Delete this chat? This cannot be undone.")) {
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

export function ChatSessionsSidebar() {
  const sessions = useChatStore((s) => s.sessions);
  const currentSessionId = useChatStore((s) => s.currentSessionId);
  const newSession = useChatStore((s) => s.newSession);
  const selectSession = useChatStore((s) => s.selectSession);
  const deleteSession = useChatStore((s) => s.deleteSession);
  const renameSession = useChatStore((s) => s.renameSession);

  const grouped = useMemo(() => {
    const sorted = [...sessions].sort(
      (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
    );
    return groupSessions(sorted);
  }, [sessions]);

  return (
    <aside className="chat-sessions-sidebar">
      <div className="chat-sessions-sidebar__header">
        <button
          type="button"
          onClick={() => newSession()}
          className="chat-sessions-sidebar__new"
        >
          <Plus className="size-3.5" />
          <span>New chat</span>
        </button>
      </div>

      <div className="chat-sessions-sidebar__list">
        {grouped.length === 0 ? (
          <div className="chat-sessions-sidebar__empty">
            <p>No chats yet</p>
            <span>Start a conversation to see it here.</span>
          </div>
        ) : (
          grouped.map((group) => (
            <div key={group.label} className="chat-sessions-sidebar__group">
              <div className="chat-sessions-sidebar__group-label">
                {group.label}
              </div>
              {group.sessions.map((s) => (
                <SessionRow
                  key={s.id}
                  session={s}
                  isSelected={s.id === currentSessionId}
                  onSelect={() => selectSession(s.id)}
                  onDelete={() => deleteSession(s.id)}
                  onRename={(t) => renameSession(s.id, t)}
                />
              ))}
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
