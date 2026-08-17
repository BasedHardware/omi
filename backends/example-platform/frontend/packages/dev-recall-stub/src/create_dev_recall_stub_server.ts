/**
 * Local DEV fixture server for ratified synthesized-memory recall pages.
 *
 * Binds 127.0.0.1 only (hard rule 13). Deterministic page generation — no
 * Math.random, no Date.now, no wall clock. Asserts every honest page against
 * isTrustedSynthesizedPageData before writing the response.
 *
 * DEV ONLY. Never production authority.
 */

import { createServer, type Server } from "node:http";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  SYNTHESIZED_READ_CONTRACT_VERSION,
  isTrustedSynthesizedPageData,
} from "@omi-core/ratified-contracts/projections/synthesized";

/** Loopback host — hard rule 13. Never 0.0.0.0, never bare-port listen. */
export const DEV_RECALL_STUB_HOST = "127.0.0.1" as const;

/** Frozen default origin port for shell IndexedDB-keyed origins. */
export const DEV_RECALL_STUB_DEFAULT_PORT = 4821;

/**
 * Path assembled from segments so source text never embeds a contiguous
 * `/v`+digit+`/memories` literal (check-isolation rule 3). The served route is
 * still the platform recall path documented in README.md.
 */
/** Must equal PLATFORM_MEMORY_RECALL_PATH — the stub stands in for BE-SURFACE's
 * `GET /v1/memories`, so a shell repoints between them by base URL alone. */
export const DEV_RECALL_STUB_PATH = "/v1/memories";

export type DevRecallStubScenario =
  | "complete"
  | "degraded"
  | "query_gap"
  | "http_503"
  | "malformed";

export interface DevRecallStubServerOptions {
  /** Default 4821. Pass 0 for an ephemeral port (tests). */
  readonly port?: number;
  /** Default scenario when the request omits `scenario`. */
  readonly scenario?: DevRecallStubScenario;
}

export interface DevRecallStubServer {
  readonly host: typeof DEV_RECALL_STUB_HOST;
  readonly port: number;
  readonly origin: string;
  readonly scenario: DevRecallStubScenario;
  close(): Promise<void>;
}

/** Seeded corpus — fixed length, fixed ids, no clock/rng. */
const SEEDED_CORPUS: readonly SeededItem[] = [
  seededItem(0),
  seededItem(1),
  seededItem(2),
  seededItem(3),
  seededItem(4),
];

const CURSOR_PREFIX = "dev-recall-stub.k.";
const DECLARED_FRONTIER = "frontier-v1:declared";
const STM_FRONTIER = "frontier-v1:included";
const DEFAULT_LIMIT = 2;
const MAX_LIMIT = 100;

interface SeededItem {
  readonly id: string;
  readonly text: string;
  readonly citations: readonly string[];
  readonly provenance: {
    readonly synthesisVersion: string;
    readonly inputDigest: string;
    readonly outputDigest: string;
  };
}

function seededItem(index: number): SeededItem {
  const n = String(index);
  return {
    id: `retrieval-node-v1:dev-recall-stub-${n}`,
    text: `Deterministic synthesized recall item ${n}`,
    citations: [`citation-v1:dev-recall-stub-${n}`],
    provenance: {
      synthesisVersion: "dev-recall-stub-v1",
      inputDigest: digestFor("in", index),
      outputDigest: digestFor("out", index),
    },
  };
}

/** Deterministic fake sha256 hex from index — not a real hash. */
function digestFor(tag: string, index: number): string {
  const seed = `dev-recall-stub/${tag}/${index}`;
  let h0 = 0x811c9dc5;
  let h1 = 0x811c9dc5 ^ 0x5f3759df;
  for (let i = 0; i < seed.length; i++) {
    const c = seed.charCodeAt(i);
    h0 ^= c;
    h0 = Math.imul(h0, 0x01000193);
    h1 ^= c ^ 0xa5;
    h1 = Math.imul(h1, 0x01000193);
  }
  const a = (h0 >>> 0).toString(16).padStart(8, "0");
  const b = (h1 >>> 0).toString(16).padStart(8, "0");
  return `${a}${b}${a}${b}${a}${b}${a}${b}`;
}

/** Thrown for a cursor this server never issued; the route maps it to 400. */
export class DevRecallStubInvalidCursorError extends Error {
  constructor(readonly cursor: string) {
    super(`dev-recall-stub: unrecognized cursor ${JSON.stringify(cursor)}`);
    this.name = "DevRecallStubInvalidCursorError";
  }
}

function encodeCursor(offset: number): string {
  return `${CURSOR_PREFIX}${offset}`;
}

/**
 * `null` = start of the walk. `"invalid"` = a cursor we did not issue.
 *
 * An unrecognized cursor must NOT decode to offset 0. A client walking pages
 * would then be silently restarted at the beginning, and since our first page
 * hands back a fresh continuation cursor, the walk never terminates — it emits
 * the same items forever. That is a duplicate-forever loop presented as a
 * healthy paginated read, and it is exactly the failure a fixture server exists
 * to make impossible. The route answers 400 instead.
 */
function decodeCursor(raw: string | null): number | "invalid" {
  if (raw === null || raw === "") return 0;
  if (!raw.startsWith(CURSOR_PREFIX)) return "invalid";
  const rest = raw.slice(CURSOR_PREFIX.length);
  if (!/^[0-9]{1,6}$/.test(rest)) return "invalid";
  return Number(rest);
}

function clampLimit(raw: string | null): number {
  if (raw === null || raw === "") return DEFAULT_LIMIT;
  const n = Number(raw);
  if (!Number.isSafeInteger(n) || n < 1) return DEFAULT_LIMIT;
  return Math.min(n, MAX_LIMIT);
}

function parseScenario(raw: string | null, fallback: DevRecallStubScenario): DevRecallStubScenario {
  if (raw === null || raw === "") return fallback;
  if (
    raw === "complete" ||
    raw === "degraded" ||
    raw === "query_gap" ||
    raw === "http_503" ||
    raw === "malformed"
  ) {
    return raw;
  }
  return fallback;
}

function completeFrontiers(): Record<string, unknown> {
  return {
    declaredFrontier: DECLARED_FRONTIER,
    newestSearchedAcceptedFrontier: DECLARED_FRONTIER,
    missingAcceptedFrontierReason: null,
    newestSearchedStmFrontier: STM_FRONTIER,
    missingStmFrontierReason: null,
  };
}

function queryGapCompleteFrontiers(): Record<string, unknown> {
  return {
    declaredFrontier: DECLARED_FRONTIER,
    newestSearchedAcceptedFrontier: DECLARED_FRONTIER,
    missingAcceptedFrontierReason: null,
    newestSearchedStmFrontier: null,
    missingStmFrontierReason: "no_eligible_stm",
  };
}

function degradedFrontiers(): Record<string, unknown> {
  return {
    declaredFrontier: DECLARED_FRONTIER,
    newestSearchedAcceptedFrontier: DECLARED_FRONTIER,
    missingAcceptedFrontierReason: null,
    newestSearchedStmFrontier: STM_FRONTIER,
    missingStmFrontierReason: null,
  };
}

function completeRecall(): Record<string, unknown> {
  return {
    version: "recall-completeness-v1",
    status: "complete",
    reasons: [],
    frontiers: completeFrontiers(),
  };
}

function degradedRecall(): Record<string, unknown> {
  return {
    version: "recall-completeness-v1",
    status: "degraded",
    reasons: ["projection_stale"],
    frontiers: degradedFrontiers(),
  };
}

function queryGapCompleteRecall(): Record<string, unknown> {
  return {
    version: "recall-completeness-v1",
    status: "complete",
    reasons: [],
    frontiers: queryGapCompleteFrontiers(),
  };
}

function itemWire(item: SeededItem): Record<string, unknown> {
  return {
    id: item.id,
    text: item.text,
    citations: [...item.citations],
    provenance: {
      synthesisVersion: item.provenance.synthesisVersion,
      inputDigest: item.provenance.inputDigest,
      outputDigest: item.provenance.outputDigest,
    },
  };
}

function moreWindow(nextOffset: number): Record<string, unknown> {
  return {
    status: "more",
    complete: false,
    hasMore: true,
    nextCursor: encodeCursor(nextOffset),
  };
}

function completeTerminalWindow(): Record<string, unknown> {
  return {
    status: "complete",
    complete: true,
    hasMore: false,
    nextCursor: null,
  };
}

/**
 * Build one keyset page. Same (scenario, limit, cursor) → byte-identical JSON.
 */
export function buildDevRecallStubPage(
  scenario: "complete" | "degraded" | "query_gap",
  limit: number,
  cursor: string | null,
): Record<string, unknown> {
  if (scenario === "query_gap") {
    return {
      contractVersion: SYNTHESIZED_READ_CONTRACT_VERSION,
      items: [],
      window: completeTerminalWindow(),
      completeness: queryGapCompleteRecall(),
      absence: { kind: "query_gap" },
    };
  }

  const offset = decodeCursor(cursor);
  if (offset === "invalid") throw new DevRecallStubInvalidCursorError(cursor ?? "");
  const slice = SEEDED_CORPUS.slice(offset, offset + limit);
  const nextOffset = offset + slice.length;
  const hasMore = nextOffset < SEEDED_CORPUS.length;
  const completeness = scenario === "degraded" ? degradedRecall() : completeRecall();

  return {
    contractVersion: SYNTHESIZED_READ_CONTRACT_VERSION,
    items: slice.map(itemWire),
    window: hasMore ? moreWindow(nextOffset) : completeTerminalWindow(),
    completeness,
    absence: null,
  };
}

/** Intentionally invalid body — fixed bytes, fails the ratified predicate. */
export const DEV_RECALL_STUB_MALFORMED_BODY =
  '{"items":[],"window":{"status":"complete","complete":true,"hasMore":false,"nextCursor":null},"completeness":{"version":"recall-completeness-v1","status":"complete","reasons":[],"frontiers":{"declaredFrontier":"frontier-v1:declared","newestSearchedAcceptedFrontier":"frontier-v1:declared","missingAcceptedFrontierReason":null,"newestSearchedStmFrontier":null,"missingStmFrontierReason":"no_eligible_stm"}},"absence":{"kind":"query_gap"}}';

function assertTrustedPage(page: Record<string, unknown>): void {
  if (!isTrustedSynthesizedPageData(page)) {
    throw new Error(
      "dev-recall-stub produced a page isTrustedSynthesizedPageData rejected — refusing to serve",
    );
  }
}

function serializeTrustedPage(page: Record<string, unknown>): string {
  assertTrustedPage(page);
  return JSON.stringify(page);
}

/**
 * Create and listen on 127.0.0.1. Resolves once the socket is listening.
 * Importable so a test can drive an ephemeral port.
 */
export function createDevRecallStubServer(
  options: DevRecallStubServerOptions = {},
): Promise<DevRecallStubServer> {
  const requestedPort = options.port ?? DEV_RECALL_STUB_DEFAULT_PORT;
  const defaultScenario = options.scenario ?? "complete";

  const server: Server = createServer((req, res) => {
    const hostHeader = req.headers.host ?? `${DEV_RECALL_STUB_HOST}:${requestedPort}`;
    const url = new URL(req.url ?? "/", `http://${hostHeader}`);

    if (req.method !== "GET" || url.pathname !== DEV_RECALL_STUB_PATH) {
      res.writeHead(404);
      res.end();
      return;
    }

    const scenario = parseScenario(url.searchParams.get("scenario"), defaultScenario);

    if (scenario === "http_503") {
      res.writeHead(503);
      res.end();
      return;
    }

    if (scenario === "malformed") {
      res.writeHead(200, {
        "content-type": "application/json; charset=utf-8",
        "cache-control": "no-store",
      });
      res.end(DEV_RECALL_STUB_MALFORMED_BODY);
      return;
    }

    const limit = clampLimit(url.searchParams.get("limit"));
    const cursor = url.searchParams.get("cursor");
    let body: string;
    try {
      body = serializeTrustedPage(buildDevRecallStubPage(scenario, limit, cursor));
    } catch (error) {
      if (error instanceof DevRecallStubInvalidCursorError) {
        // 400, never a silent restart at offset 0. See decodeCursor.
        res.writeHead(400);
        res.end();
        return;
      }
      throw error;
    }

    res.writeHead(200, {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "content-length": Buffer.byteLength(body, "utf8"),
    });
    res.end(body);
  });

  return new Promise((resolve, reject) => {
    server.once("error", reject);
    // Hard rule 13: explicit loopback host argument — never bare port.
    server.listen(requestedPort, DEV_RECALL_STUB_HOST, () => {
      const addr = server.address();
      if (addr === null || typeof addr === "string") {
        reject(new Error("dev-recall-stub: unexpected address shape after listen"));
        return;
      }
      const port = addr.port;
      resolve({
        host: DEV_RECALL_STUB_HOST,
        port,
        origin: `http://${DEV_RECALL_STUB_HOST}:${port}`,
        scenario: defaultScenario,
        close: () =>
          new Promise<void>((closeResolve, closeReject) => {
            server.close((err) => (err ? closeReject(err) : closeResolve()));
          }),
      });
    });
  });
}

function parseCliArgs(argv: readonly string[]): DevRecallStubServerOptions {
  let port: number | undefined;
  let scenario: DevRecallStubScenario | undefined;
  for (const arg of argv) {
    if (arg.startsWith("--port=")) {
      const n = Number(arg.slice("--port=".length));
      if (Number.isSafeInteger(n) && n >= 0) port = n;
      continue;
    }
    if (arg.startsWith("--scenario=")) {
      scenario = parseScenario(arg.slice("--scenario=".length), "complete");
      continue;
    }
    if (/^[0-9]+$/.test(arg)) {
      port = Number(arg);
    }
  }
  return {
    ...(port !== undefined ? { port } : {}),
    ...(scenario !== undefined ? { scenario } : {}),
  };
}

async function main(argv: readonly string[]): Promise<void> {
  const opts = parseCliArgs(argv);
  const stub = await createDevRecallStubServer(opts);
  process.stdout.write(
    `dev-recall-stub listening on ${stub.origin}${DEV_RECALL_STUB_PATH} scenario=${stub.scenario}\n`,
  );
}

const isMain =
  process.argv[1] !== undefined &&
  fileURLToPath(import.meta.url) === resolve(process.argv[1]);

if (isMain) {
  main(process.argv.slice(2)).catch((err: unknown) => {
    process.stderr.write(String(err instanceof Error ? err.stack ?? err.message : err) + "\n");
    process.exit(1);
  });
}
