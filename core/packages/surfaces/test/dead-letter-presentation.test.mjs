/**
 * THE DEAD-LETTER SURFACE, and the affordance it must never grow.
 *
 * David signed the `stale_epoch` copy in person and, in the same decision,
 * signed that this surface must not offer a "Try again". The two are one
 * mechanism: the dead envelope carries the account epoch the op was authored
 * under, so the fence refuses it forever, while a person retyping the content
 * mints a NEW op under the CURRENT epoch and succeeds. The copy therefore asks
 * for re-apply — and makes a retry button look obvious to the next person who
 * touches this file.
 *
 * The behavioural half of that pin lives in
 * `packages/testkit/src/test/platform-tasks-ops.test.ts`, which drives the real
 * outbox and asserts a stale-epoch write id is put on the wire exactly once,
 * ever, across every backoff step, re-auth, discard, and app restart. This file
 * covers the presentation seam the panels actually route through, and closes
 * with a STATIC TRIPWIRE — labelled as such, because reading source text is not
 * behavioural coverage — over the panels themselves.
 */

import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  DEAD_LETTER_AFFORDANCES,
  deadLetterSavedEdit,
  deadLetterView,
} from "../src/production/dead-letter-presentation.ts";
import { EN_MESSAGES } from "@omi-core/i18n";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

const PANELS = [
  "src/production/TasksProduction.tsx",
  "src/production/SettingsProduction.tsx",
  "src/production/MemoriesProduction.tsx",
  "src/production/ConversationsProduction.tsx",
];

const OP = { op: "patch", opId: "quiet-otter-lucid", id: "flying-dragon-vibrant", at: 1000, patch: { description: "buy milk" } };

function letter(overrides = {}) {
  return {
    opId: "quiet-otter-lucid",
    recordId: "flying-dragon-vibrant",
    domain: "tasks",
    summary: "Edit task flying-dragon-vibrant: description",
    payload: JSON.stringify(OP),
    failure: { kind: "permanent", reason: "stale_epoch", detail: "tasks/flying-dragon-vibrant" },
    deadAt: 1_700_000_000_000,
    ...overrides,
  };
}

test("the signed stale-epoch string is the catalog's, byte for byte", () => {
  // Owner-signed copy (DAVID-retention-and-refusal-copy.md §2). A delegate may
  // not edit it, so the test states it literally rather than deriving it.
  assert.equal(
    EN_MESSAGES["dead.staleEpoch"],
    "We couldn't apply this change. Your edit is saved below — paste it back in to apply it now.",
  );
  // The copy may never say `conflict` or `gone`: both are specific and false —
  // no edit won a race and the record is still there.
  assert.doesNotMatch(EN_MESSAGES["dead.staleEpoch"], /conflict|gone/i);
});

test("a stale-epoch letter renders the signed string and the saved edit beneath it", () => {
  const view = deadLetterView(letter());
  assert.equal(view.messageKey, "dead.staleEpoch");
  assert.notEqual(view.savedEdit, null, '"saved below" is a promise about the screen');
  assert.match(view.savedEdit, /buy milk/, "the actual patch fields, not a summary");
  assert.deepEqual(JSON.parse(view.savedEdit), OP, "the edit is reproducible by hand from what is shown");
  // red-proof: make deadLetterView return `savedEdit: null` unconditionally —
  // the signed string then renders over an empty panel and this fails.
  // RED-PROOF PENDING.
});

test("the signed string never renders when there is no edit to show", () => {
  // A dead letter journaled before `payload` existed. Rendering "your edit is
  // saved below" over nothing would make an owner-signed sentence false.
  const { payload, ...legacyLetter } = letter();
  void payload;
  const older = deadLetterView(legacyLetter);
  assert.equal(older.messageKey, "dead.body");
  assert.equal(older.savedEdit, null);

  // And a malformed payload is treated exactly the same, via
  // `deadLetterPayload()` — never a bare JSON.parse, which throws and takes the
  // whole panel with it.
  const malformed = deadLetterView(letter({ payload: "{not json" }));
  assert.equal(malformed.messageKey, "dead.body");
  assert.equal(malformed.savedEdit, null);
  assert.doesNotThrow(() => deadLetterSavedEdit(letter({ payload: "{not json" })));
  // red-proof: drop the `savedEdit !== null` condition from the messageKey
  // choice — both letters then render the promise with nothing beneath it.
  // RED-PROOF PENDING.
});

test("every other permanent reason keeps the long-standing generic string", () => {
  for (const reason of ["validation", "oversize", "conflict", "entitlement", "gone"]) {
    const view = deadLetterView(letter({ failure: { kind: "permanent", reason, detail: "x" } }));
    assert.equal(view.messageKey, "dead.body", `${reason} is not stale_epoch`);
    assert.equal(view.savedEdit, null, `${reason} claims nothing about a saved edit`);
  }
});

test("no dead-letter affordance can resubmit the dead envelope", () => {
  // The union is closed and has exactly one member. This is the typed half of
  // the pin: adding a resubmit affordance is not a small edit someone makes
  // while "improving" the panel, it is a change to this list that fails here.
  assert.deepEqual([...DEAD_LETTER_AFFORDANCES], ["discard"]);
  for (const affordance of DEAD_LETTER_AFFORDANCES) {
    assert.doesNotMatch(affordance, /retry|resend|resubmit|apply|send/i);
  }
  assert.deepEqual([...deadLetterView(letter()).affordances], ["discard"]);
  // red-proof: add "retry" to DEAD_LETTER_AFFORDANCES — all three assertions
  // fail. RED-PROOF PENDING.
});

test("STATIC TRIPWIRE — no production dead-letter panel wires a send to a dead letter", async () => {
  // Labelled a tripwire on purpose (AGENTS.md): it reads source text, so it is
  // not behavioural coverage. It exists because the behavioural pin above can
  // only see paths that go through the presentation seam, and the affordance a
  // future change would add is one typed straight into the JSX.
  for (const panel of PANELS) {
    const source = await read(panel);
    const deadBlock = source.slice(source.indexOf("dead.title"));
    assert.ok(deadBlock.length > 0, `${panel} renders a dead-letter panel`);
    assert.match(deadBlock, /deadLetterView/, `${panel} routes dead letters through the one decision`);
    assert.doesNotMatch(
      deadBlock,
      /common\.retry|dead\.retry|store\.(create|patch|delete)\(|resend|retryDeadLetter/,
      `${panel} offers no affordance that resubmits a dead letter`,
    );
    assert.doesNotMatch(source, /JSON\.parse\(\s*letter\.payload/, `${panel} never bare-parses a payload`);
  }
  // red-proof: add `<button onClick={() => store.patch(letter.recordId, {})}>`
  // inside TasksProduction's dead panel — the store.patch( pattern matches and
  // this fails. RED-PROOF PENDING.
});
