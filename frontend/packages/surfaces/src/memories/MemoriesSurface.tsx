/**
 * The memories surface — framework-thin by design: all behavior lives in
 * MemoriesStore; this component renders store state and calls store methods.
 * No fetch, no storage, no platform APIs in here, ever.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { DeadLetter, Memory } from "@omi-core/contracts";
import type { MemoriesStore } from "@omi-core/domain";

function MemoryRow({ memory, store }: { memory: Memory; store: MemoriesStore }): React.JSX.Element {
  const [draft, setDraft] = useState(memory.content);
  const committed = useRef(memory.content);

  useEffect(() => {
    setDraft(memory.content);
    committed.current = memory.content;
  }, [memory.content]);

  const commitContent = (): void => {
    const text = draft.trim();
    if (!text || text === committed.current) return;
    committed.current = text;
    void store.patch(memory.id, { content: text });
  };

  // A locked memory's content is a server truncation, not the record, so there
  // is no editable control at all — not a disabled one, so no commit path
  // exists to fire. MemoriesStore.patch enforces the same invariant.
  if (memory.locked) {
    return (
      <li className="locked">
        <p className="content">{memory.content}</p>
        <span className="badge locked" title="Upgrade to view and edit this memory">
          Locked
        </span>
        <button className="delete" title="Delete memory" onClick={() => void store.delete(memory.id)}>
          ×
        </button>
      </li>
    );
  }

  return (
    <li>
      <textarea
        className="content"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commitContent}
        aria-label="Memory content"
        rows={2}
      />
      <button
        className="visibility"
        title={memory.visibility === "public" ? "Make private" : "Make public"}
        onClick={() =>
          void store.patch(memory.id, { visibility: memory.visibility === "public" ? "private" : "public" })
        }
      >
        {memory.visibility === "public" ? "Public" : "Private"}
      </button>
      <button className="delete" title="Delete memory" onClick={() => void store.delete(memory.id)}>
        ×
      </button>
    </li>
  );
}

export function MemoriesSurface({ store }: { store: MemoriesStore }): React.JSX.Element {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [dead, setDead] = useState<DeadLetter[]>([]);
  const [pending, setPending] = useState(0);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const reload = useCallback(() => {
    void store.list().then(setMemories);
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

  const add = (): void => {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    void store.create(text);
    inputRef.current?.focus();
  };

  return (
    <div className="memories-surface">
      <header>
        <h1>Memories</h1>
        {pending > 0 && <span className="badge pending">{pending} syncing…</span>}
      </header>

      <form
        className="add-row"
        onSubmit={(e) => {
          e.preventDefault();
          add();
        }}
      >
        <textarea
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a memory…"
          aria-label="New memory content"
          rows={2}
        />
        <button type="submit" disabled={!draft.trim()}>
          Add
        </button>
      </form>

      <ul className="memory-list">
        {memories.map((m) => (
          <MemoryRow key={m.id} memory={m} store={store} />
        ))}
        {memories.length === 0 && <li className="empty">No memories yet — add one above.</li>}
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
