/**
 * DEV harness entry: token + base-URL form (persisted in localStorage), then
 * mounts TasksSurface and MemoriesSurface on real stores over the web storage
 * bridge. This file is the dev-mode "shell"; real shells replace everything here.
 */

import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { realEnv } from "@omi-core/kernel";
import { openWebStorageBridge } from "@omi-core/bridge-web";
import { MemoriesStore, TasksStore } from "@omi-core/domain";
import { MemoriesSurface } from "../memories/MemoriesSurface.js";
import { TasksSurface } from "../tasks/TasksSurface.js";
import { devHttpClient } from "./http.js";
import "./styles.css";

const LS_URL = "omi-dev-base-url";
const LS_TOKEN = "omi-dev-token";
const LS_UID = "omi-dev-uid";

type DevTab = "tasks" | "memories";

type DevStores = { tasks: TasksStore; memories: MemoriesStore };

function DevHarness({ stores }: { stores: DevStores }): React.JSX.Element {
  const [tab, setTab] = useState<DevTab>("tasks");

  return (
    <>
      <nav className="dev-tabs" aria-label="Surface switcher">
        <button type="button" className={tab === "tasks" ? "active" : ""} onClick={() => setTab("tasks")}>
          Tasks
        </button>
        <button type="button" className={tab === "memories" ? "active" : ""} onClick={() => setTab("memories")}>
          Memories
        </button>
      </nav>
      {tab === "tasks" ? <TasksSurface store={stores.tasks} /> : <MemoriesSurface store={stores.memories} />}
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
