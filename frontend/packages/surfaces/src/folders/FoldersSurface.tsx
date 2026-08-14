/**
 * The folders surface — framework-thin by design: all behavior lives in
 * FoldersStore; this component renders store state and calls store methods.
 * No fetch, no storage, no platform APIs in here, ever.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { DeadLetter, Folder } from "@omi-core/contracts";
import type { FoldersStore } from "@omi-core/domain";

function FolderRow({ folder, store }: { folder: Folder; store: FoldersStore }): React.JSX.Element {
  const [draft, setDraft] = useState(folder.name);
  const committed = useRef(folder.name);

  useEffect(() => {
    setDraft(folder.name);
    committed.current = folder.name;
  }, [folder.name]);

  const commitRename = (): void => {
    const text = draft.trim();
    if (!text || text === committed.current) return;
    committed.current = text;
    void store.patch(folder.id, { name: text });
  };

  return (
    <li className={folder.isSystem ? "system" : ""}>
      <span className="icon" aria-hidden>
        {folder.icon}
      </span>
      <input
        className="name"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commitRename}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commitRename();
          }
        }}
        aria-label={`Folder name: ${folder.name}`}
      />
      {folder.isDefault && <span className="badge default">Default</span>}
      {!folder.isSystem && (
        <button className="delete" title="Delete folder" onClick={() => void store.delete(folder.id)}>
          ×
        </button>
      )}
    </li>
  );
}

export function FoldersSurface({ store }: { store: FoldersStore }): React.JSX.Element {
  const [folders, setFolders] = useState<Folder[]>([]);
  const [dead, setDead] = useState<DeadLetter[]>([]);
  const [pending, setPending] = useState(0);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const reload = useCallback(() => {
    void store.list().then(setFolders);
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
    <div className="folders-surface">
      <header>
        <h1>Folders</h1>
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
          placeholder="Add a folder…"
          aria-label="New folder name"
        />
        <button type="submit" disabled={!draft.trim()}>
          Add
        </button>
      </form>

      <ul className="folder-list">
        {folders.map((f) => (
          <FolderRow key={f.id} folder={f} store={store} />
        ))}
        {folders.length === 0 && <li className="empty">No folders yet — add one above.</li>}
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
