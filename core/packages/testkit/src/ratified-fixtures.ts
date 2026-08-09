/**
 * Loader for the RATIFIED conformance corpora.
 *
 * `contracts/ratified/fixtures/` is the shared definition of correct for the
 * memory read path. The backend runs these corpora against its HTTP binding;
 * this loader is how the frontend suite runs the SAME files against the client
 * adapter. Same corpora, both ends — that is the whole mechanism behind
 * "the new backend is ready for memories" being a green suite rather than a
 * judgment call (`core/README.md`, the dual-migration rule).
 *
 * Hermetic: reads committed files from the repo, nothing else. No network, no
 * clock, no randomness. It lives in the testkit rather than in a test file
 * because it IS harness — INTEGRATION consumes it too, against a live server.
 *
 * The corpora are read from source rather than copied, deliberately. A copy
 * would drift, and a drifted corpus is worse than no corpus: it goes green
 * against a contract nobody is shipping. `core/contracts/ratified/` is owned
 * by nobody (board ruling PR-3) precisely so both ends can trust it.
 */

import { existsSync, readFileSync } from "node:fs";

/**
 * Walk up from this module to `core/contracts/ratified/fixtures/`.
 *
 * Resolved by SEARCH rather than by a fixed `../../../` count because the
 * count differs between the source tree and `dist/`, and a wrong count fails
 * at runtime with ENOENT — which, in a suite whose whole job is to run these
 * corpora, is a failure mode that would be easy to "fix" by deleting the
 * assertion. Every corpus test also asserts a minimum entry count, so an empty
 * or missing corpus can never read as a pass.
 */
const FIXTURE_DIR = locateFixtureDir();

function locateFixtureDir(): URL {
  let dir = new URL("./", import.meta.url);
  for (let up = 0; up < 8; up++) {
    const candidate = new URL("contracts/ratified/fixtures/", dir);
    if (existsSync(new URL("manifest.json", candidate))) return candidate;
    dir = new URL("../", dir);
  }
  throw new Error("could not locate core/contracts/ratified/fixtures/ above " + import.meta.url);
}

/** Every corpus named by `fixtures/manifest.json`. */
export type RatifiedCorpusName =
  | "read-page-windows"
  | "recall-completeness"
  | "recall-trace"
  | "page-conformance"
  | "status-matrix"
  | "write-ops-conformance"
  | "tasks-read-conformance";

export interface RatifiedFixtureManifest {
  readonly schemaVersion: number;
  readonly files: readonly string[];
}

export function readRatifiedFixtureManifest(): RatifiedFixtureManifest {
  return JSON.parse(readFileSync(new URL("manifest.json", FIXTURE_DIR), "utf8")) as RatifiedFixtureManifest;
}

/**
 * One corpus, as an array of entries. Returns `unknown[]` on purpose: each
 * corpus has its own entry schema, and a test that narrows it should do so
 * explicitly rather than inherit a shape this loader guessed.
 */
export function readRatifiedCorpus(name: RatifiedCorpusName): readonly unknown[] {
  const parsed: unknown = JSON.parse(readFileSync(new URL(`${name}.json`, FIXTURE_DIR), "utf8"));
  if (!Array.isArray(parsed)) {
    throw new Error(`ratified corpus ${name}.json is not an array — the corpus schema changed`);
  }
  return parsed;
}

/**
 * The write-ops SCHEMA OF RECORD — the declared outcome table the corpus is
 * checked for coverage against (`core/scripts/check-wire-conformance.mjs`).
 *
 * Read as an object rather than through `readRatifiedCorpus`, which requires
 * an array: the two files are different kinds of thing. The corpus is a list
 * of cases; this is the enumeration of everything the wire can answer, and the
 * ratified package's own test asserts it matches the module's exported tables
 * so it cannot drift into a second source of truth.
 */
export function readRatifiedWriteOpsSchema(): {
  readonly schemaVersion: number;
  readonly route: string;
  readonly writableDomains: readonly string[];
  readonly writeIdPattern: string;
  readonly writeIdEntropyBytes: number;
  readonly outcomes: readonly {
    readonly outcome: string;
    readonly kind: "accepted" | "refusal" | "error";
    readonly status: number;
    readonly body?: string;
    readonly idempotent?: boolean;
  }[];
} {
  return JSON.parse(readFileSync(new URL("write-ops-outcomes.json", FIXTURE_DIR), "utf8"));
}

/**
 * The tasks-read SCHEMA OF RECORD — the declared case and refusal tables the
 * corpus is checked for coverage against
 * (`core/scripts/check-wire-conformance.mjs`, seam `ratified-tasks-read`).
 *
 * Read as an object rather than through `readRatifiedCorpus`, which requires an
 * array: the two files are different kinds of thing. The corpus is a list of
 * cases; this is the enumeration of everything the wire can answer AND
 * everything it must refuse. The ratified package's own test asserts
 * `itemFields` equals the module's exported `TASK_ITEM_FIELDS`, so it cannot
 * drift into a second source of truth.
 */
export function readRatifiedTasksReadShape(): {
  readonly schemaVersion: number;
  readonly contractVersion: string;
  readonly completenessVersion: string;
  readonly route: string;
  readonly itemFields: readonly string[];
  readonly windowStates: readonly string[];
  readonly completenessStatuses: readonly string[];
  readonly limitationReasons: readonly string[];
  readonly missingAppliedFrontierReasons: readonly string[];
  readonly cases: readonly { readonly case: string }[];
  readonly refusalLaws: readonly { readonly case: string }[];
} {
  return JSON.parse(readFileSync(new URL("tasks-read-shape.json", FIXTURE_DIR), "utf8"));
}

/**
 * The field names a synthesized projection must NEVER expose, and the field
 * names a recall trace must never expose. Sourced from the ratified corpus so
 * the frontend cannot quietly drift from the backend's idea of "forbidden".
 *
 * `forbidden-public-fields.mjs` ships as ESM source rather than JSON, so it is
 * parsed rather than imported: importing it from here would put a
 * `contracts/ratified` specifier in a `from "…"` position, which
 * `check-isolation.mjs` reads as a traversal above `core/`.
 */
export function readRatifiedForbiddenFields(): {
  readonly projection: readonly string[];
  readonly trace: readonly string[];
} {
  const source = readFileSync(new URL("forbidden-public-fields.mjs", FIXTURE_DIR), "utf8");
  return {
    projection: extractStringArray(source, "forbiddenProjectionFields"),
    trace: extractStringArray(source, "forbiddenTraceFields"),
  };
}

function extractStringArray(source: string, exportName: string): readonly string[] {
  const start = source.indexOf(`${exportName} = [`);
  if (start < 0) throw new Error(`${exportName} not found in forbidden-public-fields.mjs`);
  const open = source.indexOf("[", start);
  const close = source.indexOf("];", open);
  if (close < 0) throw new Error(`${exportName} is not a closed array literal`);
  const body = source.slice(open + 1, close);
  const names = [...body.matchAll(/"([^"]+)"/g)].map((m) => m[1]!);
  if (names.length === 0) throw new Error(`${exportName} produced no field names`);
  return names;
}
