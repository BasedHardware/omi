/**
 * The client half of the ratified FOLDERS READ seam — rule 15's declared
 * consumer for the `ratified-folders-read` seam.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import type { HttpClient, HttpResponse } from "@omi-core/contracts";
import {
  PLATFORM_FOLDERS_MAX_LIMIT,
  PLATFORM_FOLDERS_READ_PATH,
  fetchPlatformFolderIdSnapshot,
  parsePlatformFolderPageResponse,
  platformFolderCoverageFromPage,
  platformFolderItemsFromPage,
  walkPlatformFolderPages,
} from "@omi-core/adapters-platform";
import { readRatifiedCorpus, readRatifiedFoldersReadShape } from "../ratified-fixtures.js";

interface FoldersCorpusRow {
  readonly wireCase: string;
  readonly label: string;
  readonly safe: boolean;
  readonly page: unknown;
}

const corpus = (): readonly FoldersCorpusRow[] =>
  readRatifiedCorpus("folders-read-conformance") as readonly FoldersCorpusRow[];

class ScriptedPages implements HttpClient {
  readonly paths: string[] = [];
  constructor(private readonly queue: HttpResponse[]) {}
  async request(_method: string, path: string): Promise<HttpResponse> {
    this.paths.push(path);
    const next = this.queue.shift();
    if (!next) throw new Error(`unscripted request: ${path}`);
    return next;
  }
}

class RepeatingPage implements HttpClient {
  requests = 0;
  constructor(private readonly body: unknown) {}
  async request(): Promise<HttpResponse> {
    this.requests += 1;
    return okPage(this.body);
  }
}

const okPage = (page: unknown): HttpResponse => ({
  status: 200,
  json: page,
  text: JSON.stringify(page),
});

const rowFor = (wireCase: string): FoldersCorpusRow => {
  const found = corpus().find((row) => row.wireCase === wireCase);
  assert.ok(found, `corpus row ${wireCase} is missing — the corpus changed shape`);
  return found;
};

const pageFor = (wireCase: string): Record<string, unknown> =>
  structuredClone(rowFor(wireCase).page) as Record<string, unknown>;

test("every folders corpus row is judged identically by the client adapter", () => {
  const rows = corpus();
  assert.ok(rows.length >= 30, "the folders corpus is empty or truncated — that must never read as a pass");
  for (const row of rows) {
    const overText = parsePlatformFolderPageResponse(okPage(row.page));
    assert.equal(overText.kind === "page", row.safe, `${row.wireCase} over raw text`);
    if (overText.kind === "page") assert.equal(overText.boundary, "canonical-json-text");
    const overJson = parsePlatformFolderPageResponse({
      status: 200,
      json: structuredClone(row.page),
    });
    assert.equal(overJson.kind === "page", row.safe, `${row.wireCase} over parsed json`);
    if (overJson.kind === "page") assert.equal(overJson.boundary, "trusted-parsed-json");
  }
});

test("the corpus covers every case and every refusal law the schema of record declares", () => {
  const shape = readRatifiedFoldersReadShape();
  const covered = new Set(corpus().map((row) => row.wireCase));
  assert.ok(shape.cases.length > 0 && shape.refusalLaws.length > 0, "an empty schema of record proves nothing");
  for (const { case: declared } of [...shape.cases, ...shape.refusalLaws]) {
    assert.ok(covered.has(declared), `${declared} is declared but has no corpus row`);
  }
  assert.equal(shape.route, PLATFORM_FOLDERS_READ_PATH);
});

test("all eleven fields survive the projection onto the surface type", () => {
  const shape = readRatifiedFoldersReadShape();
  const outcome = parsePlatformFolderPageResponse(okPage(pageFor("item:full_field_parity")));
  assert.equal(outcome.kind, "page");
  if (outcome.kind !== "page") return;
  const [item] = platformFolderItemsFromPage(outcome.page);
  assert.ok(item);
  assert.deepEqual(Object.keys(item).sort(), [...shape.itemFields].sort());
});

test("coverage is CARRIED from the server, never derived from the page", () => {
  const outcome = parsePlatformFolderPageResponse(okPage(pageFor("completeness:incomplete")));
  assert.equal(outcome.kind, "page");
  if (outcome.kind !== "page") return;
  const coverage = platformFolderCoverageFromPage(outcome.page);
  assert.equal(coverage.kind, "known");
  if (coverage.kind !== "known") return;
  assert.equal(coverage.hasMore, false);
  assert.equal(coverage.complete, false);
  assert.equal(coverage.status, "incomplete");
  assert.deepEqual([...coverage.reasons], ["pending_writes"]);
});

test("a walk that ends complete-terminal but passed through a lagging page is NOT the whole set", () => {
  const laggingFirst = pageFor("window:incomplete_continuation");
  const honestLast = pageFor("window:complete_terminal");
  setFirstItemId(honestLast, "other-folder-qa");
  const http = new ScriptedPages([okPage(laggingFirst), okPage(honestLast)]);
  return walkPlatformFolderPages(http).then((walk) => {
    assert.ok(walk);
    assert.equal(walk.pages, 2);
    assert.equal(walk.wholeSet, false);
    assert.equal(walk.coverage.kind === "known" && walk.coverage.complete, true);
  });
});

test("a repeated item id across pages makes the whole walk unknowable", () => {
  const first = pageFor("window:more_continuation");
  const second = pageFor("window:complete_terminal");
  const http = new ScriptedPages([okPage(first), okPage(second)]);
  return walkPlatformFolderPages(http).then((walk) => {
    assert.equal(walk, null);
  });
});

test("a server that never terminates is bounded, and never claims the set", () => {
  const repeating = new RepeatingPage(pageFor("window:more_continuation"));
  return walkPlatformFolderPages(repeating, { maxPages: 3 }).then((walk) => {
    assert.equal(walk, null);
    assert.ok(repeating.requests <= 3);
  });
});

test("an unreadable or non-200 page anywhere aborts the walk rather than truncating it", () => {
  const http = new ScriptedPages([
    okPage(pageFor("window:more_continuation")),
    { status: 503, json: null },
  ]);
  return walkPlatformFolderPages(http).then((walk) => {
    assert.equal(walk, null);
  });
});

test("an id snapshot is null, never empty-and-complete, when the walk is not honest", () => {
  const http = new ScriptedPages([{ status: 500, json: null }]);
  return fetchPlatformFolderIdSnapshot(http).then((snapshot) => {
    assert.equal(snapshot, null);
  });
});

test("an honest empty account yields a complete, empty snapshot", () => {
  const http = new ScriptedPages([okPage(pageFor("absence:query_gap"))]);
  return fetchPlatformFolderIdSnapshot(http).then((snapshot) => {
    assert.ok(snapshot);
    assert.equal(snapshot.complete, true);
    assert.deepEqual(snapshot.ids, []);
  });
});

test("the adapter asks for a limit the server will actually honor", () => {
  const http = new ScriptedPages([okPage(pageFor("window:complete_terminal"))]);
  return walkPlatformFolderPages(http, { limit: 10_000 }).then(() => {
    assert.equal(http.paths.length, 1);
    assert.match(
      http.paths[0]!,
      new RegExp(`^\\${PLATFORM_FOLDERS_READ_PATH}\\?limit=${PLATFORM_FOLDERS_MAX_LIMIT}$`),
    );
  });
});

function setFirstItemId(page: Record<string, unknown>, id: string): void {
  const items = page["items"] as { id: string }[];
  const first = items[0];
  assert.ok(first, "corpus page has no item to renumber");
  first.id = id;
}
