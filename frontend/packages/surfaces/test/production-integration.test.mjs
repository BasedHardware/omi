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
  // The bootstrap builds the PLATFORM factory for every route. Named platform
  // ports are the only live data path — the legacy generation is retired.
  assert.match(main, /createPlatformProductionStoreFactory\(/);
  assert.match(main, /platformHttp: http/);
  assert.doesNotMatch(main, /legacyHttp/);
  assert.doesNotMatch(main, /(?:Memories|Conversations|Folders|Tasks)Store\.open/);

  // Selection comes from the HOST, never from a bare user-typed URL alone, and a
  // rejection is reported rather than silently downgraded.
  assert.match(main, /__OMI_HOST_CONFIG__/);
  assert.match(main, /OMI_GENERATION_REJECTED/);
  assert.match(main, /OMI_GENERATION_SELECTION/);

  assert.match(main, /openHomeSearchSources\(platform\)/);
  assert.match(main, /markRendered\("home", memoriesGeneration/);
  assert.doesNotMatch(main, /markRendered\("home", "legacy"\)/);
  assert.doesNotMatch(main, /openMemories\(\)/);

  assert.match(main, /route === "memories"/);
  assert.match(main, /platform\.openMemoryCorrection\(\)/);
  assert.match(stores, /openMemoryCorrection\(\)/);
  assert.doesNotMatch(stores, /openMemories:/);
  const homeSources = await read("src/production/home-sources.ts");
  assert.match(homeSources, /openSynthesizedMemories\(\)/);
  assert.match(homeSources, /openPlatformConversations\(\)/);
  assert.doesNotMatch(homeSources, /openMemories\(\)/);
  assert.doesNotMatch(homeSources, /openConversations\(\)/);

  const conversationSources = await read("src/production/conversation-sources.ts");
  const folderSources = await read("src/production/folder-sources.ts");
  const taskSources = await read("src/production/task-sources.ts");
  assert.match(main, /openConversationRouteSources\(platform\)/);
  assert.match(main, /openFolderRouteSource\(platform\)/);
  assert.match(main, /openTaskRouteSource\(platform\)/);
  assert.match(conversationSources, /openPlatformConversations\(\)/);
  assert.match(conversationSources, /openPlatformFolders\(\)/);
  assert.doesNotMatch(conversationSources, /openConversations\(\)/);
  assert.match(folderSources, /openPlatformFolders\(\)/);
  assert.doesNotMatch(folderSources, /openFolders\(\)/);
  assert.match(taskSources, /openPlatformTasks\(\)/);
  assert.doesNotMatch(taskSources, /openTasks\(\)/);
  assert.doesNotMatch(main, /route === "conversations"[\s\S]{0,400}stores\.openConversations\(\)/);
  assert.doesNotMatch(main, /route === "folders"[\s\S]{0,200}stores\.openFolders\(\)/);
  assert.doesNotMatch(main, /route === "tasks"[\s\S]{0,200}stores\.openTasks\(\)/);
  assert.match(
    await read("../adapters-platform/src/conversations.ts"),
    /complete: page\.completeness\.status === "complete"/,
  );
  assert.match(
    await read("../adapters-platform/src/folders.ts"),
    /complete: page\.completeness\.status === "complete"/,
  );
  assert.match(
    await read("../adapters-platform/src/tasks.ts"),
    /complete: page\.completeness\.status === "complete"/,
  );
  assert.doesNotMatch(conversationSources, /complete:\s*(true|false|items\.length)/);
  assert.doesNotMatch(folderSources, /complete:\s*(true|false|items\.length)/);
  assert.doesNotMatch(taskSources, /complete:\s*(true|false|items\.length)/);

  assert.match(stores, /export type PlatformProductionStoreFactory/);
  assert.match(stores, /openPlatformTasks\(\)/);
  assert.doesNotMatch(stores, /createLegacyProductionStoreFactory/);
  // red-proof: constructing a concrete domain store in main bypasses the
  // single composition seam the rewritten backend must replace.
});

test("Home reuses the memory presentation rule instead of leaking provenance prefixes", async () => {
  const home = await read("src/production/HomeProduction.tsx");
  const memories = await read("src/production/MemoriesProduction.tsx");
  const presentation = await read("src/production/memory-presentation.ts");
  assert.match(home, /presentHomeMemory\(row\.value, locale\)/);
  assert.match(home, /presentMemoryContent\(hit\.text\)\.body/);
  assert.match(home, /presentPropositionContent\(hit\.text\)/);
  assert.match(memories, /presentMemoryContent\(memory\.content\)/);
  assert.match(presentation, /PROVENANCE_PREFIX/);
  // red-proof: rendering row.value.content directly puts raw `notes:` style
  // adapter metadata back into the search result's primary copy.
});
