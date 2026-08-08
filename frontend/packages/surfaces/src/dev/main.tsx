/**
 * DEV harness entry: picks an HTTP transport, then mounts every surface on real
 * stores over the web storage bridge. This file is the dev-mode "shell"; real
 * shells replace everything here.
 *
 * Transport selection is feature-detected, not configured. Hosted in a shell
 * that provides privileged HTTP, it binds `bridgeHttpClient` and no credential
 * or base URL is entered, persisted, or otherwise present in JS. In a plain
 * browser it falls back to the DEV-ONLY direct-fetch client, which is the only
 * mode with a token form. The active mode is labelled in the UI both places.
 *
 * All four stores open off ONE bridge and one http client, which is the shape a
 * real shell has too — see the multi-store co-hosting test in testkit: each
 * store must own a domain-namespaced outbox journal and projection, or they
 * replay each other's ops through the wrong transport.
 */

import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { realEnv } from "@omi-core/kernel";
import { openOnDiskFallbackSink } from "@omi-core/sync";
import { bridgeHttpClient, isBridgeHttpAvailable, openWebStorageBridge } from "@omi-core/bridge-web";
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
        <span className={BRIDGE_MODE ? "transport-badge bridge" : "transport-badge dev"} data-transport={BRIDGE_MODE ? "bridge" : "dev"}>
          {BRIDGE_MODE ? "bridge transport" : "dev transport"}
        </span>
      </nav>
      {surfaces[tab]}
    </>
  );
}

/**
 * Which transport the harness is bound to. BRIDGE is ship-shaped: the shell
 * owns the base URL and the credential, so neither exists in JS. DEV is the
 * plain-browser fallback and is the ONLY mode that ever handles a token here.
 */
const BRIDGE_MODE = isBridgeHttpAvailable();

function DevApp(): React.JSX.Element {
  const [stores, setStores] = useState<DevStores | null>(null);
  const [baseUrl, setBaseUrl] = useState(localStorage.getItem(LS_URL) ?? "https://api.omi.me");
  const [token, setToken] = useState(localStorage.getItem(LS_TOKEN) ?? "");
  const [uid, setUid] = useState(localStorage.getItem(LS_UID) ?? "dev-user");

  const connect = async (): Promise<void> => {
    localStorage.setItem(LS_UID, uid);
    // In bridge mode nothing about the endpoint or the credential is ours to
    // hold: do not persist (or even read) a base URL or token, so there is no
    // JS-visible copy to leak. Clear any left over from a previous dev session.
    if (BRIDGE_MODE) {
      localStorage.removeItem(LS_URL);
      localStorage.removeItem(LS_TOKEN);
    } else {
      localStorage.setItem(LS_URL, baseUrl);
      localStorage.setItem(LS_TOKEN, token);
    }
    const bridge = await openWebStorageBridge(uid);
    const http = BRIDGE_MODE
      ? bridgeHttpClient()
      : devHttpClient(baseUrl, () => localStorage.getItem(LS_TOKEN) ?? "");
    // COORD-degradation-is-unobservable: this is a dev/QA build, so it gets
    // the on-disk adapter — an overnight degradation should still be here
    // in the morning, not lost when the tab closes.
    const env = realEnv(await openOnDiskFallbackSink(bridge));
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
      <p className={BRIDGE_MODE ? "transport bridge" : "transport dev"} data-transport={BRIDGE_MODE ? "bridge" : "dev"}>
        {BRIDGE_MODE
          ? "Transport: BRIDGE (privileged) — the shell holds the base URL and credential; no token is entered or stored here."
          : "Transport: DEV (direct fetch) — no shell bridge on this host. DEV-ONLY: ship mode must cross the bridge."}
      </p>
      {BRIDGE_MODE ? (
        <p>Offline works too — with no reachable backend, writes queue and stay visible.</p>
      ) : (
        <>
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
        </>
      )}
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
