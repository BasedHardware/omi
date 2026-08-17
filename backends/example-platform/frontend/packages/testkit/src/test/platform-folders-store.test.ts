/**
 * Platform folders store honesty: coverage is unknown until an honest page
 * is read, and is never restored from cache.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { HttpClient, HttpResponse } from "@omi-core/contracts";
import { PlatformFoldersStore } from "@omi-core/domain";
import { readRatifiedCorpus } from "../ratified-fixtures.js";
import { ManualEnv, MemoryStore } from "../fakes.js";

interface FoldersCorpusRow {
  readonly wireCase: string;
  readonly safe: boolean;
  readonly page: unknown;
}

const pageFor = (wireCase: string): unknown => {
  const rows = readRatifiedCorpus("folders-read-conformance") as readonly FoldersCorpusRow[];
  const row = rows.find((entry) => entry.wireCase === wireCase);
  assert.ok(row, `corpus row ${wireCase} is missing`);
  return structuredClone(row.page);
};

const ok = (page: unknown): HttpResponse => ({ status: 200, json: page, text: JSON.stringify(page) });

class Scripted implements HttpClient {
  constructor(private readonly queue: HttpResponse[]) {}
  async request(): Promise<HttpResponse> {
    const next = this.queue.shift();
    if (!next) throw new Error("unscripted request");
    return next;
  }
}

const env = new ManualEnv();
const disk = (): MemoryStore => new MemoryStore();

test("coverage is unknown until an honest page is read, and is never restored from cache", async () => {
  const store = disk();
  const first = await PlatformFoldersStore.open(
    store.openBridge("u1"),
    env,
    new Scripted([ok(pageFor("window:complete_terminal"))]),
  );
  assert.equal(first.coverage().kind, "unknown");
  await first.refresh();
  assert.equal(first.coverage().kind, "known");

  const reopened = await PlatformFoldersStore.open(store.openBridge("u1"), env, new Scripted([]));
  assert.equal((await reopened.list()).length, 1, "cached items must survive a reopen");
  assert.equal(reopened.coverage().kind, "unknown", "a persisted coverage claim is not evidence about today");
});

test("a failed read drops the coverage claim but keeps the cached items", async () => {
  const store = await PlatformFoldersStore.open(disk().openBridge("u1"), env, new Scripted([
    ok(pageFor("window:complete_terminal")),
    { status: 503, json: null },
  ]));
  await store.refresh();
  assert.equal(store.coverage().kind, "known");
  await store.refresh();
  assert.equal(store.coverage().kind, "unknown");
  assert.equal((await store.list()).length, 1);
});
