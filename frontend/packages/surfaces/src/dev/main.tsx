/**
 * DEV harness entry: token + base-URL form (persisted in localStorage), then
 * mounts every surface on real stores over the web storage bridge. This file is
 * the dev-mode "shell"; real shells replace everything here.
 *
 * All four stores open off ONE bridge and one http client, which is the shape a
 * real shell has too — see the multi-store co-hosting test in testkit: each
 * store must own a domain-namespaced outbox journal and projection, or they
 * replay each other's ops through the wrong transport.
 */

import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { realEnv } from "@omi-core/kernel";
import { openWebStorageBridge } from "@omi-core/bridge-web";
import { ConversationsStore, FoldersStore, MemoriesStore, TasksStore } from "@omi-core/domain";
import { ConversationsSurface } from "../conversations/ConversationsSurface.js";
import { FoldersSurface } from "../folders/FoldersSurface.js";
import { MemoriesSurface } from "../memories/MemoriesSurface.js";
import { TasksSurface } from "../tasks/TasksSurface.js";
import { devHttpClient } from "./http.js";
import "./styles.css";

const LS_URL = "omi-dev-base-url";
const LS_TOKEN = "omi-dev-token";
const LS_UID = "omi-dev-uid";

type DevTab = "tasks" | "memories" | "conversations" | "folders";

const TAB_LABELS: Record<DevTab, string> = {
  tasks: "Tasks",
  memories: "Memories",
  conversations: "Conversations",
  folders: "Folders",
};

type DevStores = {
  tasks: TasksStore;
  memories: MemoriesStore;
  conversations: ConversationsStore;
  folders: FoldersStore;
};

function DevHarness({ stores }: { stores: DevStores }): React.JSX.Element {
  const [tab, setTab] = useState<DevTab>("tasks");

  const surfaces: Record<DevTab, React.JSX.Element> = {
    tasks: <TasksSurface store={stores.tasks} />,
    memories: <MemoriesSurface store={stores.memories} />,
    conversations: <ConversationsSurface store={stores.conversations} />,
    folders: <FoldersSurface store={stores.folders} />,
  };

  return (
    <>
      <nav className="dev-tabs" aria-label="Surface switcher">
        {(Object.keys(TAB_LABELS) as DevTab[]).map((t) => (
          <button key={t} type="button" className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
            {TAB_LABELS[t]}
          </button>
        ))}
      </nav>
      {surfaces[tab]}
    </>
  );
}

function DevApp(): React.JSX.Element {
  const [stores, setStores] = useState<DevStores | null>(null);
  const [baseUrl, setBaseUrl] = useState(localStorage.getItem(LS_URL) ?? "https://api.omi.me");
  const [token, setToken] = useState(localStorage.getItem(LS_TOKEN) ?? "");
  const [uid, setUid] = useState(localStorage.getItem(LS_UID) ?? "dev-user");

  const connect = async (): Promise<void> => {
    localStorage.setItem(LS_URL, baseUrl);
    localStorage.setItem(LS_TOKEN, token);
    localStorage.setItem(LS_UID, uid);
    const bridge = await openWebStorageBridge(uid);
    const http = devHttpClient(baseUrl, () => localStorage.getItem(LS_TOKEN) ?? "");
    const env = realEnv();
    setStores({
      tasks: await TasksStore.open(bridge, env, http),
      memories: await MemoriesStore.open(bridge, env, http),
      conversations: await ConversationsStore.open(bridge, env, http),
      folders: await FoldersStore.open(bridge, env, http),
    });
  };

  if (stores) return <DevHarness stores={stores} />;

  return (
    <div className="dev-connect">
      <h1>Omi core — dev harness</h1>
      <p>
        Dev-only entry. Paste a bearer token (grab one from an existing app session's
        Authorization header). Offline works too — leave the token blank and writes queue.
      </p>
      <label>
        Backend base URL
        <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
      </label>
      <label>
        Bearer token
        <input value={token} onChange={(e) => setToken(e.target.value)} placeholder="eyJ…" />
      </label>
      <label>
        Local profile (storage namespace)
        <input value={uid} onChange={(e) => setUid(e.target.value)} />
      </label>
      <button onClick={() => void connect()}>Open harness</button>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <DevApp />
  </StrictMode>,
);
