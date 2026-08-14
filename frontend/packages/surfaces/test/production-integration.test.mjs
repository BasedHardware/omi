import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

test("production surfaces depend on stable store ports instead of QA fixtures", async () => {
  const components = await Promise.all([
    "MemoriesProduction.tsx",
    "ConversationsProduction.tsx",
    "TasksProduction.tsx",
  ].map((name) => read(`src/production/${name}`)));
  for (const source of components) {
    assert.match(source, /from "\.\/ProductionStores\.js"/);
    assert.doesNotMatch(source, /Production(?:Memory|Conversation|Folder|Task)Store[^;]+fixtures\.js/);
  }
  // red-proof: moving a store interface back into a fixture module makes the
  // backend generation boundary depend on QA-only implementation details.
});

test("Listen live composition stays on the ratified platform stream while polish fixtures remain explicit", async () => {
  const [main, listen, store] = await Promise.all([
    read("src/production/main.tsx"),
    read("src/production/ListenProduction.tsx"),
    read("src/production/createPlatformListenStore.ts"),
  ]);
  assert.match(main, /createPlatformListenCaptureClient/);
  assert.match(main, /createPlatformProductionListenStore/);
  assert.match(main, /__OMI_LISTEN_PROTOCOL_SCHEMA__/);
  assert.match(main, /route === "listen"/);
  assert.match(main, /requestedQa === "listen" && LISTEN_FIXTURE_STATES\.includes/);
  assert.match(main, /fixtureListenStore\(listenFixture\)/);
  assert.match(main, /source=\{\{ kind: "fixture", fixture: evidenceLabel \}\}/);
  assert.match(listen, /source = \{ kind: "live", origin: "bridge" \}/);
  assert.match(listen, /data-qa-fixture=\{fixture \?\? "none"\}/);
  assert.match(listen, /ProductionDataSourceBadge/);
  assert.match(store, /platformListenCaptureState/);
  // red-proof: letting the evidence fixture become a default or bypassing the
  // typed platform client makes the production composition assertions fail.
});

test("every live route adopts the shared source, lifecycle, and live-boundary primitives", async () => {
  const routeFiles = [
    "HomeProduction.tsx",
    "MemoriesProduction.tsx",
    "TasksProduction.tsx",
    "ConversationsProduction.tsx",
    "FoldersProduction.tsx",
    "ChatProduction.tsx",
    "ListenProduction.tsx",
    "SettingsProduction.tsx",
  ];
  const sources = await Promise.all(routeFiles.map((name) => read(`src/production/${name}`)));
  for (const source of sources) {
    assert.match(source, /ProductionDataSourceBadge/);
    assert.match(source, /ProductionLifecycleRegion/);
    assert.match(source, /surface-notices/);
  }
  for (const source of sources.filter((_, index) => [0, 5, 6, 7].includes(index))) {
    assert.match(source, /ProductionLiveAnnouncement/);
  }
  // The route render suites exercise the concrete stores; this guard prevents
  // a new route from silently bypassing the shared contracts.
});

test("live Chat and Settings are composed through their ratified stores and native hosts", async () => {
  const main = await read("src/production/main.tsx");
  assert.match(main, /bridgeStreamPort\(\)/);
  assert.match(main, /bridgeChatAttachmentStagingPort\(\)/);
  assert.match(main, /platform\.openChat\(\)/);
  assert.match(main, /createPlatformProductionSettingsStore\(http,/);
  assert.match(main, /<ChatProduction store=\{store\}/);
  assert.match(main, /<SettingsProduction store=\{store\}/);
  assert.doesNotMatch(main, /route === "chat"[\s\S]{0,500}fixtureChatStore/);
  assert.doesNotMatch(main, /route === "settings"[\s\S]{0,500}fixtureSettingsStore/);
  // red-proof: route Chat or Settings through the final Memories branch, omit
  // either native Chat port, or substitute a fixture store. The composition
  // assertions fail before a native shell can claim the route.
});

test("bootstrap chooses backend generation through one production factory", async () => {
  const main = await read("src/production/main.tsx");
  const stores = await read("src/production/ProductionStores.ts");
  // The bootstrap now builds the PLATFORM factory for every route. It extends the legacy
  // factory, so legacy domains are unchanged — which is exactly what lets Memories move
  // generation while Tasks/Conversations/Folders stay put (board ruling PR-1).
  // The factory receives the ALREADY-RESOLVED selection, not the raw host input: the route
  // is computed from that same selection, so resolving twice risks the two disagreeing.
  assert.match(main, /createPlatformProductionStoreFactory\(/);
  assert.match(main, /legacyHttp: http/);
  assert.match(main, /platformHttp: http/);
  assert.doesNotMatch(main, /(?:Memories|Conversations|Folders|Tasks)Store\.open/);

  // Selection comes from the HOST, never from a bare user-typed URL alone, and a
  // rejection is reported rather than silently downgraded.
  assert.match(main, /__OMI_HOST_CONFIG__/);
  assert.match(main, /OMI_GENERATION_REJECTED/);
  assert.match(main, /OMI_GENERATION_SELECTION/);

  // The platform read model is reachable ONLY on the memories route. Rendering it for any
  // selected generation would hijack Home/Tasks/Conversations with a Memories screen.
  // Routing itself — including the default that makes a bare `generation=platform` land
  // here at all — is covered behaviorally in production-routing.test.mjs.
  assert.match(main, /route === "memories" && platform\.selection\.memories === "platform"/);
  // red-proof: dropping the `route === "memories"` conjunct makes `?generation=platform`
  // render propositions on every route, including Tasks. Dropping the REJECTED log lets a
  // client believe it is on the new backend while reading the legacy wire — the single
  // worst outcome available here.

  assert.match(stores, /export type ProductionStoreFactory/);
  assert.match(stores, /openMemories\(\)/);
  assert.match(stores, /openConversations\(\)/);
  assert.match(stores, /openFolders\(\)/);
  assert.match(stores, /openTasks\(\)/);
  // red-proof: constructing a concrete domain store in main bypasses the
  // single composition seam the rewritten backend must replace.
});

test("Home reuses the memory presentation rule instead of leaking provenance prefixes", async () => {
  const home = await read("src/production/HomeProduction.tsx");
  const memories = await read("src/production/MemoriesProduction.tsx");
  const presentation = await read("src/production/memory-presentation.ts");
  assert.match(home, /presentMemoryContent\(row\.value\.content\)\.body/);
  assert.match(memories, /presentMemoryContent\(memory\.content\)/);
  assert.match(presentation, /PROVENANCE_PREFIX/);
  // red-proof: rendering row.value.content directly puts raw `notes:` style
  // adapter metadata back into the search result's primary copy.
});
