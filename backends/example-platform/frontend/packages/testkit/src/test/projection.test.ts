/**
 * Projection conformance: durable offline reads (ADR-004 D1) and the
 * finding-9 reconcile rule — honest clients never delete on partial info.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import { Projection, type ProjectionCodec } from "@omi-core/sync";
import { MemoryStore } from "../fakes.js";

interface Row {
  id: string;
  text: string;
  done?: boolean;
}

const codec: ProjectionCodec<Row> = {
  id: (r) => r.id,
  applyOp: (payload, current) => {
    const op = JSON.parse(payload) as { kind: string; id: string; text?: string; done?: boolean };
    if (op.kind === "create") return { id: op.id, text: op.text ?? "" };
    if (op.kind === "delete") return null;
    if (!current) return current;
    const patched: Row = { ...current };
    if (op.text !== undefined) patched.text = op.text;
    if (op.done !== undefined) patched.done = op.done;
    return patched;
  },
};

test("cold offline launch shows previously synced rows (ADR-004 D1)", async () => {
  const store = new MemoryStore();
  const bridge1 = store.openBridge("user-a");
  const p1 = await Projection.open(await bridge1.openKv("tasks"), codec);
  await p1.upsertServerRows([{ id: "amber-fox-ridge", text: "ship the exemplar" }]);

  // App killed; relaunch with NO network (nothing calls upsert):
  const bridge2 = store.openBridge("user-a");
  const p2 = await Projection.open(await bridge2.openKv("tasks"), codec);
  const rows = await p2.read([]);
  assert.deepEqual(rows, [{ id: "amber-fox-ridge", text: "ship the exemplar" }]);
});

test("incomplete id snapshot never deletes (red-team finding 9)", async () => {
  const store = new MemoryStore();
  const p = await Projection.open(await store.openBridge("u").openKv("tasks"), codec);
  await p.upsertServerRows([
    { id: "amber-fox-ridge", text: "a" },
    { id: "cedar-owl-brook", text: "b" },
  ]);

  const partial = await p.reconcile({ setVersion: "v1", complete: false, ids: ["amber-fox-ridge"] });
  assert.deepEqual(partial.deletedIds, [], "partial snapshot removed nothing");

  const full = await p.reconcile({ setVersion: "v2", complete: true, ids: ["amber-fox-ridge"] });
  assert.deepEqual(full.deletedIds, ["cedar-owl-brook"], "complete snapshot deletes honestly");

  const replayed = await p.reconcile({ setVersion: "v2", complete: true, ids: [] });
  assert.deepEqual(replayed.deletedIds, [], "same setVersion never re-applies");
});

test("pending overlays render over server truth and unwind cleanly", async () => {
  const store = new MemoryStore();
  const p = await Projection.open(await store.openBridge("u").openKv("tasks"), codec);
  await p.upsertServerRows([{ id: "amber-fox-ridge", text: "original" }]);

  const withOverlay = await p.read([
    { recordId: "amber-fox-ridge", payload: JSON.stringify({ kind: "patch", id: "amber-fox-ridge", done: true }) },
    { recordId: "delta-kite-moss", payload: JSON.stringify({ kind: "create", id: "delta-kite-moss", text: "new" }) },
  ]);
  assert.equal(withOverlay.length, 2);
  assert.equal(withOverlay.find((r) => r.id === "amber-fox-ridge")?.done, true);

  // Overlays gone (confirmed or dead) — server truth is untouched:
  const clean = await p.read([]);
  assert.deepEqual(clean, [{ id: "amber-fox-ridge", text: "original" }]);
});
