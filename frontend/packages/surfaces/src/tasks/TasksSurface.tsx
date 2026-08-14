/**
 * The tasks surface — the exemplar shared UI. Framework-thin by design: all
 * behavior lives in TasksStore; this component renders store state and calls
 * store methods. No fetch, no storage, no platform APIs in here, ever.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { DeadLetter, Task } from "@omi-core/contracts";
import type { TasksStore } from "@omi-core/domain";

export function TasksSurface({ store }: { store: TasksStore }): React.JSX.Element {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [dead, setDead] = useState<DeadLetter[]>([]);
  const [pending, setPending] = useState(0);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(() => {
    void store.list().then(setTasks);
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
    <div className="tasks-surface">
      <header>
        <h1>Tasks</h1>
        {pending > 0 && <span className="badge pending">{pending} syncing…</span>}
      </header>

      <form
        className="add-row"
        onSubmit={(e) => {
          e.preventDefault();
          add();
        }}
      >
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a task…"
          aria-label="New task description"
        />
        <button type="submit" disabled={!draft.trim()}>
          Add
        </button>
      </form>

      <ul className="task-list">
        {tasks.map((t) => (
          <li key={t.id} className={t.completed ? "done" : ""}>
            <label>
              <input
                type="checkbox"
                checked={t.completed}
                onChange={() => void store.patch(t.id, { completed: !t.completed })}
              />
              <span className="desc">{t.description}</span>
            </label>
            {t.dueAt !== null && <span className="due">{new Date(t.dueAt).toLocaleDateString()}</span>}
            <button className="delete" title="Delete task" onClick={() => void store.delete(t.id)}>
              ×
            </button>
          </li>
        ))}
        {tasks.length === 0 && <li className="empty">No tasks yet — add one above.</li>}
      </ul>

      {dead.length > 0 && (
        <section className="dead-letters" aria-label="Unsent items">
          <h2>Couldn’t sync ({dead.length})</h2>
          <ul>
            {dead.map((d) => (
              <li key={d.opId}>
                <span className="summary">{d.summary}</span>
                <span className="reason">{d.failure.reason}: {d.failure.detail}</span>
                <button onClick={() => void store.discardDeadLetter(d.opId).then(reload)}>Discard</button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
