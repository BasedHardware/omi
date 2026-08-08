/**
 * Half (A): oracle self-check.
 *
 * Runs every ratified fixture-corpus entry through the matching vendored
 * validator and asserts the verdict equals the corpus boolean. This proves the
 * oracle itself is intact — not that any HTTP server is correct.
 */

import { parseKeysetCursor } from "@omi-core/ratified-contracts/pagination/cursor";
import {
  isTrustedPageWindowHonest,
  isTrustedRecallCompletenessHonest,
  isTrustedSynthesizedPageData,
  parseSynthesizedPageJson,
} from "@omi-core/ratified-contracts/projections/synthesized";
import {
  isTrustedRecallTraceData,
  parseRecallTraceJson,
} from "@omi-core/ratified-contracts/recall/trace";

import type { CorpusOracleResult, OracleEntryFailure, OracleReport } from "./report.ts";

export const RATIFIED_PACKAGE_ROOT = new URL(
  "../../node_modules/@omi-core/ratified-contracts/",
  import.meta.url,
);

export const FIXTURES_ROOT = new URL("fixtures/", RATIFIED_PACKAGE_ROOT);

export type FixtureManifest = {
  readonly schemaVersion: number;
  readonly files: readonly string[];
};

export type NamedSafePage = {
  readonly name: string;
  readonly page: unknown;
  readonly safe: boolean;
};

export type NamedHonestWindow = {
  readonly name: string;
  readonly window: {
    status: string;
    complete: boolean;
    hasMore: boolean;
    nextCursor: string | null;
  };
  readonly honest: boolean;
};

export type NamedHonestCompleteness = {
  readonly name: string;
  readonly page: Parameters<typeof isTrustedRecallCompletenessHonest>[0];
  readonly honest: boolean;
};

export type NamedSafeTrace = {
  readonly name: string;
  readonly trace: unknown;
  readonly safe: boolean;
};

export type StatusMatrixRow = {
  readonly window:
    | "complete_terminal"
    | "more_continuation"
    | "incomplete_terminal"
    | "incomplete_continuation";
  readonly completeness: "complete" | "incomplete" | "degraded" | "partial";
  readonly empty?: boolean;
  readonly queryGap?: boolean;
  readonly safe: boolean;
};

export async function loadFixtureJson<T>(name: string): Promise<T> {
  const file = Bun.file(new URL(name, FIXTURES_ROOT));
  if (!(await file.exists())) {
    throw new Error(`ratified fixture missing on disk: ${name}`);
  }
  return (await file.json()) as T;
}

export async function loadManifest(): Promise<FixtureManifest> {
  return await loadFixtureJson<FixtureManifest>("manifest.json");
}

function entryName(row: { name?: string }, index: number, corpus: string): string {
  if (typeof row.name === "string" && row.name.length > 0) return row.name;
  return `${corpus}[${index}]`;
}

function corpusResult(
  corpus: string,
  total: number,
  failures: OracleEntryFailure[],
): CorpusOracleResult {
  const mismatched = failures.length;
  return {
    corpus,
    total,
    matched: total - mismatched,
    mismatched,
    failures,
  };
}

/** page-conformance.json: isTrustedSynthesizedPageData + parseSynthesizedPageJson */
export async function checkPageConformanceCorpus(): Promise<CorpusOracleResult> {
  const rows = await loadFixtureJson<NamedSafePage[]>("page-conformance.json");
  const failures: OracleEntryFailure[] = [];
  for (const [index, row] of rows.entries()) {
    const name = entryName(row, index, "page-conformance");
    const trusted = isTrustedSynthesizedPageData(row.page);
    const parsed = parseSynthesizedPageJson(JSON.stringify(row.page)) !== null;
    const actual = trusted && parsed;
    if (actual !== row.safe) {
      failures.push({
        name,
        expected: row.safe,
        actual,
        detail: `isTrustedSynthesizedPageData=${trusted}, parseSynthesizedPageJson ok=${parsed}`,
      });
    }
  }
  return corpusResult("page-conformance.json", rows.length, failures);
}

/** read-page-windows.json: isTrustedPageWindowHonest */
export async function checkReadPageWindowsCorpus(): Promise<CorpusOracleResult> {
  const rows = await loadFixtureJson<NamedHonestWindow[]>("read-page-windows.json");
  const failures: OracleEntryFailure[] = [];
  for (const [index, row] of rows.entries()) {
    const name = entryName(row, index, "read-page-windows");
    const actual = isTrustedPageWindowHonest(row.window);
    if (actual !== row.honest) {
      failures.push({
        name,
        expected: row.honest,
        actual,
        detail: `window status=${row.window.status} complete=${row.window.complete} hasMore=${row.window.hasMore} nextCursor=${row.window.nextCursor === null ? "null" : "present"}`,
      });
    }
  }
  return corpusResult("read-page-windows.json", rows.length, failures);
}

/** recall-completeness.json: isTrustedRecallCompletenessHonest */
export async function checkRecallCompletenessCorpus(): Promise<CorpusOracleResult> {
  const rows = await loadFixtureJson<NamedHonestCompleteness[]>("recall-completeness.json");
  const failures: OracleEntryFailure[] = [];
  for (const [index, row] of rows.entries()) {
    const name = entryName(row, index, "recall-completeness");
    const actual = isTrustedRecallCompletenessHonest(row.page);
    if (actual !== row.honest) {
      failures.push({
        name,
        expected: row.honest,
        actual,
        detail: `completeness status=${row.page.completeness?.status ?? "<missing>"}`,
      });
    }
  }
  return corpusResult("recall-completeness.json", rows.length, failures);
}

/** recall-trace.json: isTrustedRecallTraceData + parseRecallTraceJson */
export async function checkRecallTraceCorpus(): Promise<CorpusOracleResult> {
  const rows = await loadFixtureJson<NamedSafeTrace[]>("recall-trace.json");
  const failures: OracleEntryFailure[] = [];
  for (const [index, row] of rows.entries()) {
    const name = entryName(row, index, "recall-trace");
    const trusted = isTrustedRecallTraceData(row.trace);
    const parsed = parseRecallTraceJson(JSON.stringify(row.trace)) !== null;
    const actual = trusted && parsed;
    if (actual !== row.safe) {
      failures.push({
        name,
        expected: row.safe,
        actual,
        detail: `isTrustedRecallTraceData=${trusted}, parseRecallTraceJson ok=${parsed}`,
      });
    }
  }
  return corpusResult("recall-trace.json", rows.length, failures);
}

/** Build the page object implied by a status-matrix row (same construction as package tests). */
export function buildStatusMatrixPage(row: StatusMatrixRow): unknown {
  const windows = {
    complete_terminal: { status: "complete", complete: true, hasMore: false, nextCursor: null },
    more_continuation: {
      status: "more",
      complete: false,
      hasMore: true,
      nextCursor: "v1.signature.payload",
    },
    incomplete_terminal: {
      status: "incomplete",
      complete: false,
      hasMore: false,
      nextCursor: null,
    },
    incomplete_continuation: {
      status: "incomplete",
      complete: false,
      hasMore: true,
      nextCursor: "v1.signature.payload",
    },
  } as const;
  const complete = {
    version: "recall-completeness-v1",
    status: "complete",
    reasons: [],
    frontiers: {
      declaredFrontier: "frontier-v1:declared",
      newestSearchedAcceptedFrontier: row.empty ? null : "frontier-v1:declared",
      missingAcceptedFrontierReason: row.empty ? "no_accepted_work" : null,
      newestSearchedStmFrontier: row.empty ? null : "frontier-v1:included",
      missingStmFrontierReason: row.empty ? "no_eligible_stm" : null,
    },
  } as const;
  const limitations = {
    incomplete: ["accepted_work_pending", "accepted_work_pending"],
    degraded: ["projection_unavailable", "projection_unavailable"],
    partial: ["source_bound", "source_bound"],
  } as const;
  const completeness =
    row.completeness === "complete"
      ? complete
      : {
          version: "recall-completeness-v1",
          status: row.completeness,
          reasons: [limitations[row.completeness][0]],
          frontiers: {
            declaredFrontier: "frontier-v1:declared",
            newestSearchedAcceptedFrontier:
              row.completeness === "incomplete" ? "frontier-v1:behind" : "frontier-v1:declared",
            missingAcceptedFrontierReason: null,
            newestSearchedStmFrontier: null,
            missingStmFrontierReason: limitations[row.completeness][1],
          },
        };
  return {
    contractVersion: "1.0.0",
    items: row.empty ? [] : [{ id: "retrieval-node-v1:fixture", text: "Synthesized result" }],
    window: windows[row.window],
    completeness,
    absence: row.queryGap ? { kind: "query_gap" } : null,
  };
}

export function statusMatrixEntryName(row: StatusMatrixRow, index: number): string {
  const empty = row.empty ? "+empty" : "";
  const gap = row.queryGap ? "+queryGap" : "";
  return `status-matrix[${index}] ${row.window}/${row.completeness}${empty}${gap}`;
}

/** status-matrix.json: reconstruct pages and assert isTrustedSynthesizedPageData */
export async function checkStatusMatrixCorpus(): Promise<CorpusOracleResult> {
  const rows = await loadFixtureJson<StatusMatrixRow[]>("status-matrix.json");
  const failures: OracleEntryFailure[] = [];
  for (const [index, row] of rows.entries()) {
    const name = statusMatrixEntryName(row, index);
    const page = buildStatusMatrixPage(row);
    const actual = isTrustedSynthesizedPageData(page);
    if (actual !== row.safe) {
      failures.push({
        name,
        expected: row.safe,
        actual,
        detail: `reconstructed ${row.window} + ${row.completeness} page disagreed with corpus.safe`,
      });
    }
    // Continuations in the matrix use a transport-shaped cursor token.
    if (row.window === "more_continuation" || row.window === "incomplete_continuation") {
      if (parseKeysetCursor("v1.signature.payload") === null) {
        failures.push({
          name,
          expected: true,
          actual: false,
          detail: "matrix continuation cursor token failed parseKeysetCursor",
        });
      }
    }
  }
  return corpusResult("status-matrix.json", rows.length, failures);
}

/** Run every corpus listed in the packaged manifest. */
export async function runOracleSelfCheck(): Promise<OracleReport> {
  const manifest = await loadManifest();
  const expected = [
    "read-page-windows.json",
    "recall-completeness.json",
    "recall-trace.json",
    "page-conformance.json",
    "status-matrix.json",
  ];
  if (JSON.stringify(manifest.files) !== JSON.stringify(expected)) {
    return {
      ok: false,
      corpora: [
        {
          corpus: "manifest.json",
          total: 1,
          matched: 0,
          mismatched: 1,
          failures: [
            {
              name: "files",
              expected: true,
              actual: false,
              detail: `manifest.files drifted: ${JSON.stringify(manifest.files)}`,
            },
          ],
        },
      ],
    };
  }

  const checkers: Record<string, () => Promise<CorpusOracleResult>> = {
    "page-conformance.json": checkPageConformanceCorpus,
    "read-page-windows.json": checkReadPageWindowsCorpus,
    "recall-completeness.json": checkRecallCompletenessCorpus,
    "recall-trace.json": checkRecallTraceCorpus,
    "status-matrix.json": checkStatusMatrixCorpus,
  };

  const corpora: CorpusOracleResult[] = [];
  for (const file of manifest.files) {
    const check = checkers[file];
    if (!check) {
      corpora.push({
        corpus: file,
        total: 1,
        matched: 0,
        mismatched: 1,
        failures: [
          {
            name: file,
            expected: true,
            actual: false,
            detail: "no oracle checker registered for this corpus file",
          },
        ],
      });
      continue;
    }
    corpora.push(await check());
  }

  return {
    ok: corpora.every((c) => c.mismatched === 0),
    corpora,
  };
}
