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
  assert.match(main, /createLegacyProductionStoreFactory\(bridge, env, http\)/);
  assert.doesNotMatch(main, /(?:Memories|Conversations|Folders|Tasks)Store\.open/);
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
