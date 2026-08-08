/**
 * Executes the five ratified fixture corpora — twice.
 *
 * (A) ORACLE SELF-CHECK. Every corpus entry is pushed through the matching
 *     validator from the VENDORED package the backend actually consumes
 *     (@omi-core/ratified-contracts 0.1.1, hash-pinned by contracts.lock.json)
 *     and the verdict must equal the corpus's own boolean. This proves the
 *     oracle is intact and the vendored copy has not drifted from the corpus.
 *     A conformance suite whose oracle is wrong is worse than no suite.
 *
 * (B) LIVE-WIRE NEGATIVE CHECK. Every corpus entry marked unsafe/dishonest is
 *     a shape the server must never emit. We paginate a LIVE server to
 *     exhaustion and assert no emitted page matches any negative shape, and
 *     that every emitted page passes the positive validators. This is the half
 *     an in-process suite cannot do, because the subject is the response bytes.
 *
 * The corpora are read from node_modules — deliberately. That is the copy the
 * backend is pinned to, so drift between it and core/contracts/ratified/ shows
 * up here rather than in production.
 */

import { readFileSync } from "node:fs";

import { afterAll, beforeAll, describe, expect, test } from "bun:test";

import {
  isTrustedPageWindowHonest,
  isTrustedRecallCompletenessHonest,
  isTrustedSynthesizedPageData,
  parseSynthesizedPageJson,
} from "@omi-core/ratified-contracts/projections/synthesized";
import { parseKeysetCursor } from "@omi-core/ratified-contracts/pagination/cursor";
import { isTrustedRecallTraceData } from "@omi-core/ratified-contracts/recall/trace";

import { callTool, control, pageTextOf, startLiveServer, type LiveServer } from "./live-server";

const FIXTURES = new URL(
  "../../node_modules/@omi-core/ratified-contracts/fixtures/",
  import.meta.url,
).pathname;

function corpus<T>(name: string): T[] {
  return JSON.parse(readFileSync(`${FIXTURES}${name}`, "utf8")) as T[];
}

let server: LiveServer;

beforeAll(async () => {
  server = await startLiveServer();
});

afterAll(async () => {
  await server?.stop();
});

describe("(A) oracle self-check — vendored validators vs the ratified corpora", () => {
  /**
   * red-proof: invert the expectation (compare to `!entry.honest`) and every
   * corpus entry mismatches. More usefully: swapping the vendored tarball for
   * a drifted build makes the specific drifted rows fail BY NAME, which is the
   * failure mode this exists to catch.
   */
  test("read-page-windows: window honesty verdicts match the corpus", () => {
    const entries = corpus<{ name: string; window: Record<string, unknown>; honest: boolean }>(
      "read-page-windows.json",
    );
    expect(entries.length).toBeGreaterThan(0);

    const mismatches = entries.filter((entry) => {
      const verdict = isTrustedPageWindowHonest(
        entry.window as unknown as {
          status: string; complete: boolean; hasMore: boolean; nextCursor: string | null;
        },
      );
      return verdict !== entry.honest;
    });
    expect(mismatches.map((entry) => entry.name)).toEqual([]);
  });

  test("recall-completeness: completeness honesty verdicts match the corpus", () => {
    const entries = corpus<{ name: string; page: Record<string, unknown>; honest: boolean }>(
      "recall-completeness.json",
    );
    expect(entries.length).toBeGreaterThan(0);

    const mismatches = entries.filter((entry) => {
      const verdict = isTrustedRecallCompletenessHonest(
        entry.page as unknown as { items: readonly unknown[] },
      );
      return verdict !== entry.honest;
    });
    expect(mismatches.map((entry) => entry.name)).toEqual([]);
  });

  test("page-conformance: page safety verdicts match the corpus", () => {
    const entries = corpus<{ name: string; page: unknown; safe: boolean }>("page-conformance.json");
    expect(entries.length).toBeGreaterThan(0);

    const mismatches = entries.filter(
      (entry) => isTrustedSynthesizedPageData(entry.page) !== entry.safe,
    );
    expect(mismatches.map((entry) => entry.name)).toEqual([]);
  });

  test("recall-trace: trace safety verdicts match the corpus", () => {
    const entries = corpus<{ name: string; trace: unknown; safe: boolean }>("recall-trace.json");
    expect(entries.length).toBeGreaterThan(0);

    const mismatches = entries.filter(
      (entry) => isTrustedRecallTraceData(entry.trace) !== entry.safe,
    );
    expect(mismatches.map((entry) => entry.name)).toEqual([]);
  });

  test("status-matrix: every window/completeness combination is classified", () => {
    const entries = corpus<{ window: string; completeness: string; safe: boolean }>(
      "status-matrix.json",
    );
    // The matrix is the specification of which pairings are legal. Assert the
    // content: an incomplete-terminal window may never carry complete recall.
    const illegal = entries.filter(
      (entry) =>
        entry.window.startsWith("incomplete") && entry.completeness === "complete" && entry.safe,
    );
    expect(illegal).toEqual([]);
    expect(entries.some((entry) => entry.safe)).toBe(true);
    expect(entries.some((entry) => !entry.safe)).toBe(true);
  });
});

describe("(B) live wire — the server can never emit a corpus negative", () => {
  /**
   * red-proof: in compose.ts `buildPage`, add any field the ratified item shape
   * forbids (e.g. `evidence: "raw"` on an item, which page-conformance.json
   * lists as unsafe). parseSynthesizedPageJson then returns null for every
   * emitted page and this fails on page 1.
   */
  test("every page emitted by the live server passes the ratified validators", async () => {
    await control(server.baseUrl, "/qa/reset?seed=7");

    const negativeWindows = corpus<{ name: string; window: Record<string, unknown>; honest: boolean }>(
      "read-page-windows.json",
    )
      .filter((entry) => !entry.honest)
      .map((entry) => JSON.stringify(entry.window));

    let cursor: string | null = null;
    let pages = 0;

    for (let guard = 0; guard < 20; guard += 1) {
      const response: { status: number; text: string } = await callTool(server.baseUrl, {
        cursor,
        limit: 2,
      });
      const pageText = pageTextOf(response.text);
      expect(pageText).not.toBeNull();

      // The authoritative untrusted-bytes boundary, fed the EXACT wire text.
      const parsed = parseSynthesizedPageJson(pageText as string);
      expect(parsed).not.toBeNull();

      const page = JSON.parse(pageText as string) as {
        window: Record<string, unknown> & { nextCursor: string | null };
        items: readonly unknown[];
      };

      expect(isTrustedPageWindowHonest(page.window as never)).toBe(true);
      expect(isTrustedRecallCompletenessHonest(page as never)).toBe(true);

      // No emitted window may equal a corpus negative.
      expect(negativeWindows).not.toContain(JSON.stringify(page.window));

      if (page.window.nextCursor !== null) {
        expect(parseKeysetCursor(page.window.nextCursor as string)).not.toBeNull();
      }

      pages += 1;
      cursor = page.window.nextCursor;
      if (cursor === null) {
        break;
      }
    }

    // Content only a working paginating server produces: it took more than one
    // page and it terminated. (Not a row count — a terminated traversal.)
    expect(pages).toBeGreaterThan(1);
    expect(cursor).toBeNull();
  });
});
