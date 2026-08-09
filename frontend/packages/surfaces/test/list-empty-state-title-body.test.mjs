import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

/**
 * Extract the true-empty JSX branch gated by refresh ready + zero loaded rows.
 * Count expression differs by surface (rows vs messages); the gate shape does not.
 */
function trueEmptyBranch(source, countExpr) {
  const marker = `status.refresh.phase === "ready" && ${countExpr} === 0 ?`;
  const start = source.indexOf(marker);
  assert.notEqual(start, -1, `missing true-empty gate for ${countExpr}`);
  const after = source.slice(start + marker.length);
  // Consequent ends at the ternary's colon. Surfaces keep this consequent free of
  // nested ternaries, so the first top-level " :" after the "?" is the separator.
  const end = after.search(/\s*:/);
  assert.notEqual(end, -1, `true-empty consequent for ${countExpr} has no ternary separator`);
  return after.slice(0, end).trim();
}

const LIST_SURFACES = [
  {
    file: "src/production/TasksProduction.tsx",
    countExpr: "rows.length",
    titleKey: "tasks.emptyTitle",
    bodyKey: "tasks.emptyBody",
  },
  {
    file: "src/production/ChatProduction.tsx",
    countExpr: "messages.length",
    titleKey: "chat.emptyTitle",
    bodyKey: "chat.emptyBody",
  },
  {
    file: "src/production/MemoriesProduction.tsx",
    countExpr: "rows.length",
    titleKey: "memories.emptyTitle",
    bodyKey: "memories.emptyBody",
  },
  {
    file: "src/production/ConversationsProduction.tsx",
    countExpr: "rows.length",
    titleKey: "conversations.emptyTitle",
    bodyKey: "conversations.emptyBody",
  },
];

test("every list surface true-empty state renders both its title and its body key", async () => {
  for (const surface of LIST_SURFACES) {
    const source = await read(surface.file);
    const branch = trueEmptyBranch(source, surface.countExpr);
    // Filter-miss (common.noResults) is a different claim — assert it out of the
    // true-empty branch before checking title/body so a retargeted empty state
    // fails on that distinction rather than only on a missing key.
    assert.doesNotMatch(
      branch,
      /common\.noResults/,
      `${surface.file} true-empty branch must not use common.noResults (that is the filter-miss claim); got: ${branch}`,
    );
    assert.match(
      branch,
      new RegExp(surface.titleKey.replace(/\./g, "\\.")),
      `${surface.file} true-empty branch must render ${surface.titleKey}; got: ${branch}`,
    );
    assert.match(
      branch,
      new RegExp(surface.bodyKey.replace(/\./g, "\\.")),
      `${surface.file} true-empty branch must render ${surface.bodyKey}; got: ${branch}`,
    );
  }
  // red-proof: (1) drop memories.emptyTitle from MemoriesProduction's ready&&rows===0
  // branch → titleKey assertion fails. (2) retarget ConversationsProduction's
  // true-empty consequent at common.noResults → bodyKey and/or noResults assertions fail.
});
