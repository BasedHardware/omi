/**
 * The conversations surface — framework-thin by design: all behavior lives in
 * ConversationsStore; this component renders store state and calls store
 * methods. No fetch, no storage, no platform APIs in here, ever.
 *
 * No create form: conversations are server-originated. Locked rows render
 * read-only (legacy 402 entitlement on detail/mutate) — the adapter maps 402
 * to permanent/entitlement; this surface keeps the edit path from firing.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { Conversation, DeadLetter } from "@omi-core/contracts";
import type { ConversationsStore } from "@omi-core/domain";

function ConversationRow({
  conversation,
  store,
}: {
  conversation: Conversation;
  store: ConversationsStore;
}): React.JSX.Element {
  const [draft, setDraft] = useState(conversation.title);
  const committed = useRef(conversation.title);

  useEffect(() => {
    setDraft(conversation.title);
    committed.current = conversation.title;
  }, [conversation.title]);

  const commitTitle = (): void => {
    const text = draft.trim();
    if (!text || text === committed.current) return;
    committed.current = text;
    void store.patch(conversation.id, { title: text });
  };

  const timestamp = conversation.updatedAt || conversation.createdAt;

  if (conversation.isLocked) {
    return (
      <li className="locked">
        <span className="title">{conversation.title || "(untitled)"}</span>
        <span className="status">{conversation.status}</span>
        {timestamp > 0 && <span className="when">{new Date(timestamp).toLocaleString()}</span>}
        <span className="badge locked" title="Upgrade to view and edit this conversation">
          Locked
        </span>
        <button className="delete" title="Delete conversation" onClick={() => void store.delete(conversation.id)}>
          ×
        </button>
      </li>
    );
  }

  return (
    <li>
      <input
        className="title"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commitTitle}
        aria-label="Conversation title"
      />
      <span className="status">{conversation.status}</span>
      {timestamp > 0 && <span className="when">{new Date(timestamp).toLocaleString()}</span>}
      <button className="delete" title="Delete conversation" onClick={() => void store.delete(conversation.id)}>
        ×
      </button>
    </li>
  );
}

export function ConversationsSurface({ store }: { store: ConversationsStore }): React.JSX.Element {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [dead, setDead] = useState<DeadLetter[]>([]);
  const [pending, setPending] = useState(0);

  const reload = useCallback(() => {
    void store.list().then(setConversations);
    void store.deadLetters().then(setDead);
    setPending(store.pendingCount());
  }, [store]);

  useEffect(() => {
    reload();
    const unsubscribe = store.subscribe(reload);
    void store.refresh();
    const interval = setInterval(() => void store.refresh(), 30_000);
    return () => {
      unsubscribe();
      clearInterval(interval);
    };
  }, [store, reload]);

  return (
    <div className="conversations-surface">
      <header>
        <h1>Conversations</h1>
        {pending > 0 && <span className="badge pending">{pending} syncing…</span>}
      </header>

      <ul className="conversation-list">
        {conversations.map((c) => (
          <ConversationRow key={c.id} conversation={c} store={store} />
        ))}
        {conversations.length === 0 && <li className="empty">No conversations yet.</li>}
      </ul>

      {dead.length > 0 && (
        <section className="dead-letters" aria-label="Unsent items">
          <h2>Couldn’t sync ({dead.length})</h2>
          <ul>
            {dead.map((d) => (
              <li key={d.opId}>
                <span className="summary">{d.summary}</span>
                <span className="reason">
                  {d.failure.reason}: {d.failure.detail}
                </span>
                <button onClick={() => void store.discardDeadLetter(d.opId).then(reload)}>Discard</button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
