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

test("bootstrap chooses backend generation through one production factory", async () => {
  const main = await read("src/production/main.tsx");
  const stores = await read("src/production/ProductionStores.ts");
  // The bootstrap now builds the PLATFORM factory for every route. It extends the legacy
  // factory, so legacy domains are unchanged — which is exactly what lets Memories move
  // generation while Tasks/Conversations/Folders stay put (board ruling PR-1).
  // The factory receives the ALREADY-RESOLVED selection, not the raw host input: the route
  // is computed from that same selection, so resolving twice risks the two disagreeing.
  assert.match(main, /createPlatformProductionStoreFactory\(bridge, env, \{ legacyHttp: http, platformHttp: http \}, generationSelection\)/);
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
