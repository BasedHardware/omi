/**
 * ⚠ UNREFERENCED, AND WRITTEN AGAINST A RETIRED FIXTURE GRAMMAR.
 *
 * Two facts, both established by grep across `platform/` and
 * `core-foundation/` on 2026-08-08, neither one a judgement:
 *
 *  1. Nothing imports `runLiveConformance` or any other export of
 *     `integration/conformance/`. No test, script, Makefile target,
 *     `dev-stack.sh` path or lane runs it. `integration/adversarial/
 *     corpus-oracle.test.ts` covers the (A) oracle self-check and the (B)
 *     live-wire negative check this file's header describes.
 *  2. Its `/qa/*` calls below use the RETIRED door's control-plane grammar
 *     (`hidden=<row id>`, `omit=<row id>`, `/qa/insert?id=&sortKey=`) and its
 *     `retrieval-node-v1:seed-NNNN` item ids. The W4 rebuild replaced both:
 *     the harness now serves the registered composition, whose public item ids
 *     are reader-scoped opaque refs, and the control plane is counted
 *     (`hidden=<count>`, `/qa/grow?by=`).
 *
 * So this cannot run as written, and the DOOR lane deliberately did not
 * "fix" it: repairing 800 lines of a runner nobody executes would produce an
 * unverified claim, which is the thing this program exists to stop. Flagged
 * for delete-or-revive as its own work item. Do not cite it as evidence.
 */
/**
 * Half (B): live-wire conformance.
 *
 * Drives a real HTTP server, takes response bytes, and feeds them through the
 * same ratified validators. Retarget with OMI_CONFORMANCE_BASE_URL (default
 * http://127.0.0.1:4851; BE-SURFACE often binds 4811).
 */

import { parseKeysetCursor } from "@omi-core/ratified-contracts/pagination/cursor";
import {
  isTrustedPageWindowHonest,
  isTrustedRecallCompletenessHonest,
  parseSynthesizedPageJson,
  type SynthesizedMemoryRead,
} from "@omi-core/ratified-contracts/projections/synthesized";

import {
  loadFixtureJson,
  type NamedHonestCompleteness,
  type NamedHonestWindow,
  type NamedSafePage,
  type StatusMatrixRow,
  buildStatusMatrixPage,
  statusMatrixEntryName,
} from "./oracle.ts";
import {
  GUARANTEE_IDS,
  allGuaranteesSkipped,
  guaranteeResult,
  liveReportOk,
  type GuaranteeId,
  type GuaranteeResult,
  type LiveReport,
} from "./report.ts";

export const DEFAULT_CONFORMANCE_BASE_URL = "http://127.0.0.1:4851";
export const QA_API_KEY = "omi-integration-qa-key-v1";
export const QA_API_KEY_OTHER_OWNER = "omi-integration-qa-key-v2";
export const MCP_PROTOCOL_VERSION = "2026-07-28";
export const MCP_TOOL = "read_synthesized_memory";

export function resolveConformanceBaseUrl(
  env: NodeJS.ProcessEnv = process.env,
): string {
  const raw = env.OMI_CONFORMANCE_BASE_URL?.trim();
  if (raw && raw.length > 0) return raw.replace(/\/$/, "");
  return DEFAULT_CONFORMANCE_BASE_URL;
}

type JsonRpcSuccess = {
  readonly jsonrpc: "2.0";
  readonly id: string | number;
  readonly result: {
    readonly resultType: string;
    readonly content: ReadonlyArray<{ readonly type: string; readonly text: string }>;
  };
};

type JsonRpcError = {
  readonly jsonrpc: "2.0";
  readonly id: string | number | null;
  readonly error: {
    readonly code: number;
    readonly message: string;
  };
};

export type McpCallResult =
  | { readonly kind: "page"; readonly status: number; readonly pageText: string; readonly page: SynthesizedMemoryRead.Page }
  | { readonly kind: "rpc_error"; readonly status: number; readonly error: JsonRpcError["error"]; readonly body: unknown }
  | { readonly kind: "transport_error"; readonly detail: string };

function mcpHeaders(apiKey: string): HeadersInit {
  return {
    accept: "application/json, text/event-stream",
    authorization: apiKey,
    "content-type": "application/json",
    "mcp-method": "tools/call",
    "mcp-name": MCP_TOOL,
    "mcp-protocol-version": MCP_PROTOCOL_VERSION,
  };
}

function readBody(limit: number, cursor?: string): unknown {
  const arguments_: Record<string, unknown> = { limit };
  if (cursor !== undefined) arguments_.cursor = cursor;
  return {
    jsonrpc: "2.0",
    id: "1",
    method: "tools/call",
    params: {
      name: MCP_TOOL,
      arguments: arguments_,
      _meta: {
        "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
        "io.modelcontextprotocol/clientCapabilities": {},
      },
    },
  };
}

export async function qaGet(
  baseUrl: string,
  pathAndQuery: string,
): Promise<{ status: number; body: unknown }> {
  const response = await fetch(`${baseUrl}${pathAndQuery}`, {
    method: "GET",
    headers: { accept: "application/json" },
  });
  const text = await response.text();
  let body: unknown = text;
  try {
    body = JSON.parse(text) as unknown;
  } catch {
    // leave as text
  }
  return { status: response.status, body };
}

/** Probe whether a conformance target is accepting QA control traffic. */
export async function probeLiveServer(
  baseUrl: string,
  timeoutMs = 750,
): Promise<{ ok: true } | { ok: false; reason: string }> {
  try {
    const response = await fetch(`${baseUrl}/qa/stats`, {
      method: "GET",
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!response.ok) {
      return { ok: false, reason: `GET /qa/stats returned HTTP ${response.status}` };
    }
    const body = (await response.json()) as { rows?: unknown };
    if (typeof body.rows !== "number") {
      return { ok: false, reason: "GET /qa/stats JSON missing numeric rows field" };
    }
    return { ok: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return { ok: false, reason: message };
  }
}

export async function callReadSynthesizedMemory(
  baseUrl: string,
  options: {
    readonly limit?: number;
    readonly cursor?: string;
    readonly apiKey?: string;
  } = {},
): Promise<McpCallResult> {
  const limit = options.limit ?? 3;
  const apiKey = options.apiKey ?? QA_API_KEY;
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/mcp`, {
      method: "POST",
      headers: mcpHeaders(apiKey),
      body: JSON.stringify(readBody(limit, options.cursor)),
    });
  } catch (err) {
    return {
      kind: "transport_error",
      detail: err instanceof Error ? err.message : String(err),
    };
  }

  const rawText = await response.text();
  let body: unknown;
  try {
    body = JSON.parse(rawText) as unknown;
  } catch {
    return {
      kind: "transport_error",
      detail: `non-JSON MCP response (HTTP ${response.status}): ${rawText.slice(0, 200)}`,
    };
  }

  if (
    body !== null &&
    typeof body === "object" &&
    "error" in body &&
    (body as JsonRpcError).error !== undefined
  ) {
    const errorBody = body as JsonRpcError;
    return {
      kind: "rpc_error",
      status: response.status,
      error: errorBody.error,
      body,
    };
  }

  const success = body as JsonRpcSuccess;
  const pageText = success?.result?.content?.[0]?.text;
  if (typeof pageText !== "string") {
    return {
      kind: "transport_error",
      detail: `MCP success missing result.content[0].text (HTTP ${response.status})`,
    };
  }

  // Feed the EXACT wire string — never a re-serialized object.
  const page = parseSynthesizedPageJson(pageText);
  if (page === null) {
    return {
      kind: "transport_error",
      detail: "wire page text failed parseSynthesizedPageJson (canonical contract reject)",
    };
  }

  return { kind: "page", status: response.status, pageText, page };
}

export type ExhaustionResult = {
  readonly pages: ReadonlyArray<{
    readonly pageText: string;
    readonly page: SynthesizedMemoryRead.Page;
  }>;
  readonly itemIds: readonly string[];
  readonly terminal: SynthesizedMemoryRead.Page;
};

/**
 * Paginate to exhaustion following real nextCursor values.
 * Asserts each page validates and the terminal window is genuinely terminal.
 */
export async function paginateToExhaustion(
  baseUrl: string,
  limit = 3,
  apiKey = QA_API_KEY,
): Promise<ExhaustionResult | { error: string }> {
  const pages: Array<{ pageText: string; page: SynthesizedMemoryRead.Page }> = [];
  const itemIds: string[] = [];
  let cursor: string | undefined;
  const maxPages = 32;

  for (let i = 0; i < maxPages; i += 1) {
    const result = await callReadSynthesizedMemory(baseUrl, { limit, cursor, apiKey });
    if (result.kind !== "page") {
      return {
        error:
          result.kind === "rpc_error"
            ? `pagination hit RPC error ${result.error.code} ${result.error.message}`
            : result.detail,
      };
    }
    pages.push({ pageText: result.pageText, page: result.page });
    for (const item of result.page.items) itemIds.push(item.id);

    const window = result.page.window;
    if (!window.hasMore) {
      return { pages, itemIds, terminal: result.page };
    }
    if (window.nextCursor === null) {
      return { error: "continuation window hasMore=true but nextCursor=null" };
    }
    const branded = parseKeysetCursor(window.nextCursor);
    if (branded === null) {
      return { error: `nextCursor failed parseKeysetCursor: ${window.nextCursor.slice(0, 64)}…` };
    }
    cursor = window.nextCursor;
  }
  return { error: `pagination exceeded ${maxPages} pages without a terminal window` };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Structural window fingerprint used to detect dishonest corpus shapes on the wire. */
function windowFingerprint(window: {
  status: string;
  complete: boolean;
  hasMore: boolean;
  nextCursor: string | null;
}): string {
  const cursorKind =
    window.nextCursor === null ? "null" : window.nextCursor.length === 0 ? "empty" : "present";
  const extraKeys = Object.keys(window)
    .filter((k) => !["status", "complete", "hasMore", "nextCursor"].includes(k))
    .sort();
  return JSON.stringify({
    status: window.status,
    complete: window.complete,
    hasMore: window.hasMore,
    cursorKind,
    extraKeys,
  });
}

function pageDefectSignature(page: unknown): string | null {
  if (!isRecord(page)) return "non-object-page";
  const items = page.items;
  if (!Array.isArray(items)) return "missing-items";

  for (const item of items) {
    if (!isRecord(item)) continue;
    if ("evidence" in item) return "item-has-evidence";
    if ("content" in item) return "item-has-legacy-content";
    if (item.id === "" || item.text === "") return "empty-branded-strings";
    const citations = item.citations;
    if (Array.isArray(citations)) {
      const seen = new Set<string>();
      for (const c of citations) {
        if (typeof c === "string") {
          if (seen.has(c)) return "duplicate-citations";
          seen.add(c);
        }
      }
    }
  }

  const ids = items
    .filter(isRecord)
    .map((item) => item.id)
    .filter((id): id is string => typeof id === "string");
  if (new Set(ids).size !== ids.length) return "duplicate-item-ids";

  const completeness = page.completeness;
  if (isRecord(completeness) && "raw" in completeness) return "completeness-extra-raw";

  const window = page.window;
  const absence = page.absence;
  if (
    isRecord(window) &&
    window.hasMore === true &&
    isRecord(absence) &&
    absence.kind === "query_gap"
  ) {
    return "query-gap-with-continuation";
  }

  return null;
}

function completenessFingerprint(
  page: Parameters<typeof isTrustedRecallCompletenessHonest>[0],
): string {
  return JSON.stringify({
    itemCount: page.items.length,
    completeness: page.completeness ?? null,
    absence: page.absence ?? null,
  });
}

/**
 * Assert no negative corpus shape appears on collected live pages.
 * Returns a failure detail string, or null when clean.
 */
export async function findNegativeCorpusOnWire(
  livePages: ReadonlyArray<SynthesizedMemoryRead.Page>,
): Promise<string | null> {
  const dishonestWindows = (
    await loadFixtureJson<NamedHonestWindow[]>("read-page-windows.json")
  ).filter((row) => !row.honest);
  const dishonestCompleteness = (
    await loadFixtureJson<NamedHonestCompleteness[]>("recall-completeness.json")
  ).filter((row) => !row.honest);
  const unsafePages = (
    await loadFixtureJson<NamedSafePage[]>("page-conformance.json")
  ).filter((row) => !row.safe);
  const unsafeMatrix = (
    await loadFixtureJson<StatusMatrixRow[]>("status-matrix.json")
  ).filter((row) => !row.safe);

  for (const live of livePages) {
    const liveFp = windowFingerprint(live.window);
    for (const row of dishonestWindows) {
      if (liveFp === windowFingerprint(row.window)) {
        return `dishonest window corpus entry "${row.name}" shape appeared on the wire`;
      }
    }

    const liveCompletenessPage = {
      items: live.items,
      completeness: live.completeness,
      absence: live.absence,
    };
    // Only flag when the live page fails honesty AND matches a negative fingerprint.
    if (!isTrustedRecallCompletenessHonest(liveCompletenessPage)) {
      const liveCfp = completenessFingerprint(liveCompletenessPage);
      for (const row of dishonestCompleteness) {
        if (liveCfp === completenessFingerprint(row.page)) {
          return `dishonest completeness corpus entry "${row.name}" shape appeared on the wire`;
        }
      }
      return "live page failed isTrustedRecallCompletenessHonest (completeness honesty)";
    }

    const defect = pageDefectSignature(live);
    if (defect !== null) {
      for (const row of unsafePages) {
        if (pageDefectSignature(row.page) === defect) {
          return `unsafe page corpus entry "${row.name}" defect (${defect}) appeared on the wire`;
        }
      }
      return `unsafe page defect (${defect}) appeared on the wire`;
    }

    // Status-matrix negatives: incomplete window + complete recall, etc.
    for (const [index, row] of unsafeMatrix.entries()) {
      const reconstructed = buildStatusMatrixPage(row) as {
        window: SynthesizedMemoryRead.Page["window"];
        completeness: SynthesizedMemoryRead.Page["completeness"];
      };
      if (
        live.window.status === reconstructed.window.status &&
        live.window.complete === reconstructed.window.complete &&
        live.window.hasMore === reconstructed.window.hasMore &&
        live.completeness.status === reconstructed.completeness.status &&
        live.window.status === "incomplete" &&
        live.completeness.status === "complete"
      ) {
        return `unsafe status-matrix entry ${statusMatrixEntryName(row, index)} pattern on the wire`;
      }
    }
  }

  return null;
}

function fail(id: GuaranteeId, detail: string): GuaranteeResult {
  return guaranteeResult(id, "failed", detail);
}

function pass(id: GuaranteeId, detail: string): GuaranteeResult {
  return guaranteeResult(id, "passed", detail);
}

async function checkCompletenessHonesty(baseUrl: string): Promise<GuaranteeResult> {
  const reset = await qaGet(baseUrl, "/qa/reset?seed=7");
  if (reset.status !== 200) {
    return fail("completeness_honesty", `qa/reset failed HTTP ${reset.status}`);
  }

  const exhaustion = await paginateToExhaustion(baseUrl, 3);
  if ("error" in exhaustion) {
    return fail("completeness_honesty", `paginate failed: ${exhaustion.error}`);
  }

  for (const { pageText, page } of exhaustion.pages) {
    // Re-parse the exact bytes again — the content-only proof.
    if (parseSynthesizedPageJson(pageText) === null) {
      return fail(
        "completeness_honesty",
        "wire page text failed parseSynthesizedPageJson on re-check",
      );
    }
    if (!isTrustedPageWindowHonest(page.window)) {
      return fail(
        "completeness_honesty",
        `window failed isTrustedPageWindowHonest: ${JSON.stringify(page.window)}`,
      );
    }
    if (
      !isTrustedRecallCompletenessHonest({
        items: page.items,
        completeness: page.completeness,
        absence: page.absence,
      })
    ) {
      return fail(
        "completeness_honesty",
        `completeness failed isTrustedRecallCompletenessHonest on page with ${page.items.length} items`,
      );
    }
  }

  const terminal = exhaustion.terminal.window;
  if (
    !(
      terminal.status === "complete" &&
      terminal.complete === true &&
      terminal.hasMore === false &&
      terminal.nextCursor === null
    )
  ) {
    return fail(
      "completeness_honesty",
      `terminal page is not a genuine terminal window: ${JSON.stringify(terminal)}`,
    );
  }

  const negative = await findNegativeCorpusOnWire(exhaustion.pages.map((p) => p.page));
  if (negative !== null) {
    return fail("completeness_honesty", negative);
  }

  // Hidden must be byte-identical to physically absent (authorization non-oracle).
  const hiddenId = "retrieval-node-v1:seed-0003";
  await qaGet(baseUrl, `/qa/reset?seed=7&hidden=${encodeURIComponent(hiddenId)}`);
  const hiddenCall = await callReadSynthesizedMemory(baseUrl, { limit: 10 });
  await qaGet(baseUrl, `/qa/absent?seed=7&omit=${encodeURIComponent(hiddenId)}`);
  const absentCall = await callReadSynthesizedMemory(baseUrl, { limit: 10 });
  if (hiddenCall.kind !== "page" || absentCall.kind !== "page") {
    return fail(
      "completeness_honesty",
      "hidden/absent probes did not both return validated pages",
    );
  }
  if (hiddenCall.pageText !== absentCall.pageText) {
    return fail(
      "completeness_honesty",
      "authorization-hidden row is distinguishable from physically absent row on the wire (oracle leak)",
    );
  }
  if (hiddenCall.page.items.some((item) => item.id === hiddenId)) {
    return fail(
      "completeness_honesty",
      "hidden id still appeared in items — visibility filter did not remove it before emission",
    );
  }

  return pass(
    "completeness_honesty",
    `all ${exhaustion.pages.length} wire pages passed parseSynthesizedPageJson + honest window/completeness; terminal is complete; hidden≡absent bytes; no negative corpus shape on wire`,
  );
}

async function checkCursorValidity(baseUrl: string): Promise<GuaranteeResult> {
  await qaGet(baseUrl, "/qa/reset?seed=7");
  const first = await callReadSynthesizedMemory(baseUrl, { limit: 3 });
  if (first.kind !== "page") {
    return fail("cursor_validity", "first page did not return a validated page");
  }
  if (!first.page.window.hasMore || first.page.window.nextCursor === null) {
    return fail(
      "cursor_validity",
      "expected a continuation cursor on seed=7 limit=3, got a terminal window",
    );
  }
  const cursor = first.page.window.nextCursor;
  if (parseKeysetCursor(cursor) === null) {
    return fail("cursor_validity", "nextCursor failed parseKeysetCursor");
  }

  const second = await callReadSynthesizedMemory(baseUrl, { limit: 3, cursor });
  if (second.kind !== "page") {
    return fail(
      "cursor_validity",
      `continuation with real cursor failed: ${second.kind === "rpc_error" ? second.error.message : second.detail}`,
    );
  }
  // Content proof: continuation must advance past the first page's last id.
  const firstIds = first.page.items.map((i) => i.id);
  const secondIds = second.page.items.map((i) => i.id);
  if (secondIds.some((id) => firstIds.includes(id))) {
    return fail(
      "cursor_validity",
      `continuation re-emitted an id from the prior page (${secondIds.join(",")}) — cursor did not advance the keyset`,
    );
  }
  if (secondIds.length === 0) {
    return fail("cursor_validity", "continuation returned an empty page unexpectedly");
  }

  return pass(
    "cursor_validity",
    `nextCursor passed parseKeysetCursor and continuation advanced past [${firstIds.join(", ")}] to [${secondIds.join(", ")}]`,
  );
}

async function checkKeysetStability(baseUrl: string): Promise<GuaranteeResult> {
  await qaGet(baseUrl, "/qa/reset?seed=7");

  // Baseline: every originally-seeded id under keyset pagination.
  const baseline = await paginateToExhaustion(baseUrl, 3);
  if ("error" in baseline) {
    return fail("keyset_stability", `baseline pagination failed: ${baseline.error}`);
  }
  const originalIds = [...baseline.itemIds];
  if (originalIds.length !== 7) {
    return fail(
      "keyset_stability",
      `expected 7 seeded ids in baseline, got ${originalIds.length}: ${originalIds.join(",")}`,
    );
  }

  await qaGet(baseUrl, "/qa/reset?seed=7");
  const page1 = await callReadSynthesizedMemory(baseUrl, { limit: 3 });
  if (page1.kind !== "page" || page1.page.window.nextCursor === null) {
    return fail("keyset_stability", "page1 did not yield a continuation cursor");
  }

  // Insert BETWEEN seed-0002 (s00000020) and seed-0003 (s00000030).
  // Offset pagination would shift and skip; keyset must still surface every original.
  const insertedId = "retrieval-node-v1:inserted-mid";
  await qaGet(
    baseUrl,
    `/qa/insert?id=${encodeURIComponent(insertedId)}&sortKey=${encodeURIComponent("s00000025")}`,
  );

  const rest = await paginateToExhaustionFrom(
    baseUrl,
    page1.page.window.nextCursor,
    3,
  );
  if ("error" in rest) {
    return fail("keyset_stability", `post-insert pagination failed: ${rest.error}`);
  }

  const seen = new Set<string>([
    ...page1.page.items.map((i) => i.id),
    ...rest.itemIds,
  ]);
  const missing = originalIds.filter((id) => !seen.has(id));
  if (missing.length > 0) {
    return fail(
      "keyset_stability",
      `insert mid-pagination skipped originally-present row(s): ${missing.join(", ")} — keyset stability broken (offset-like behavior)`,
    );
  }
  if (!seen.has(insertedId)) {
    return fail(
      "keyset_stability",
      "inserted mid-keyset row never appeared on a later page (insert was lost or filtered)",
    );
  }

  return pass(
    "keyset_stability",
    `mid-pagination insert at s00000025 did not skip any of [${originalIds.join(", ")}]; inserted id also surfaced`,
  );
}

async function paginateToExhaustionFrom(
  baseUrl: string,
  startCursor: string,
  limit: number,
): Promise<ExhaustionResult | { error: string }> {
  const pages: Array<{ pageText: string; page: SynthesizedMemoryRead.Page }> = [];
  const itemIds: string[] = [];
  let cursor: string | undefined = startCursor;
  for (let i = 0; i < 32; i += 1) {
    const result = await callReadSynthesizedMemory(baseUrl, { limit, cursor });
    if (result.kind !== "page") {
      return {
        error:
          result.kind === "rpc_error"
            ? `${result.error.code} ${result.error.message}`
            : result.detail,
      };
    }
    pages.push({ pageText: result.pageText, page: result.page });
    for (const item of result.page.items) itemIds.push(item.id);
    if (!result.page.window.hasMore) {
      return { pages, itemIds, terminal: result.page };
    }
    if (result.page.window.nextCursor === null) {
      return { error: "hasMore without nextCursor" };
    }
    if (parseKeysetCursor(result.page.window.nextCursor) === null) {
      return { error: "continuation cursor failed parseKeysetCursor" };
    }
    cursor = result.page.window.nextCursor;
  }
  return { error: "too many pages" };
}

async function checkRevisionMonotonicity(baseUrl: string): Promise<GuaranteeResult> {
  await qaGet(baseUrl, "/qa/reset?seed=7");
  const exhaustion = await paginateToExhaustion(baseUrl, 3);
  if ("error" in exhaustion) {
    return fail("revision_monotonicity", exhaustion.error);
  }

  const ids = exhaustion.itemIds;
  if (new Set(ids).size !== ids.length) {
    return fail(
      "revision_monotonicity",
      `duplicate item ids across pages (revision/order went backwards or repeated): ${ids.join(", ")}`,
    );
  }

  // Seed ids encode order; require strict ascending by the numeric suffix.
  const suffixes = ids.map((id) => {
    const match = /seed-(\d+)$/.exec(id);
    return match ? Number(match[1]) : null;
  });
  if (suffixes.some((s) => s === null)) {
    return fail(
      "revision_monotonicity",
      `unexpected id shape in pagination stream: ${ids.join(", ")}`,
    );
  }
  for (let i = 1; i < suffixes.length; i += 1) {
    if ((suffixes[i] as number) <= (suffixes[i - 1] as number)) {
      return fail(
        "revision_monotonicity",
        `item order not strictly ascending at index ${i}: ${ids[i - 1]} then ${ids[i]}`,
      );
    }
  }

  return pass(
    "revision_monotonicity",
    `pagination emitted ${ids.length} unique ids in strict ascending seed order`,
  );
}

async function checkClientIdIdempotency(baseUrl: string): Promise<GuaranteeResult> {
  await qaGet(baseUrl, "/qa/reset?seed=7");

  // Same credentials + args must yield byte-identical page text (fixture clock is fixed).
  const a = await callReadSynthesizedMemory(baseUrl, { limit: 3 });
  const b = await callReadSynthesizedMemory(baseUrl, { limit: 3 });
  if (a.kind !== "page" || b.kind !== "page") {
    return fail("client_id_idempotency", "replay probes did not both return validated pages");
  }
  if (a.pageText !== b.pageText) {
    return fail(
      "client_id_idempotency",
      "identical client request under the same identity produced different page bytes (idempotency broken)",
    );
  }

  // Cursor minted for owner-1 must be rejected for owner-2 (identity fence).
  if (a.page.window.nextCursor === null) {
    return fail("client_id_idempotency", "expected continuation cursor to probe owner fence");
  }
  const cross = await callReadSynthesizedMemory(baseUrl, {
    limit: 3,
    cursor: a.page.window.nextCursor,
    apiKey: QA_API_KEY_OTHER_OWNER,
  });
  if (cross.kind !== "rpc_error") {
    return fail(
      "client_id_idempotency",
      "cursor minted for qa-owner-1 was accepted under qa-owner-2 — client-id fence failed",
    );
  }
  if (cross.error.message !== "Invalid cursor" || cross.error.code !== -32602) {
    return fail(
      "client_id_idempotency",
      `cross-owner cursor produced unexpected error envelope: ${JSON.stringify(cross.error)}`,
    );
  }

  return pass(
    "client_id_idempotency",
    "same-identity replay is byte-identical; cross-owner cursor is rejected as Invalid cursor",
  );
}

async function checkErrorEnvelope(baseUrl: string): Promise<GuaranteeResult> {
  await qaGet(baseUrl, "/qa/reset?seed=7");
  const bogus = await callReadSynthesizedMemory(baseUrl, {
    limit: 3,
    cursor: "not-a-real-cursor",
  });
  if (bogus.kind !== "rpc_error") {
    return fail(
      "error_envelope",
      `bogus cursor must yield a JSON-RPC error envelope, got kind=${bogus.kind}`,
    );
  }
  if (bogus.status !== 400) {
    return fail(
      "error_envelope",
      `Invalid cursor must be HTTP 400, got ${bogus.status}`,
    );
  }
  if (bogus.error.code !== -32602 || bogus.error.message !== "Invalid cursor") {
    return fail(
      "error_envelope",
      `wrong error payload: ${JSON.stringify(bogus.error)}`,
    );
  }
  // Must not look like a successful page wrapper.
  if (
    bogus.body !== null &&
    typeof bogus.body === "object" &&
    "result" in (bogus.body as object)
  ) {
    return fail(
      "error_envelope",
      "error response also carried a result field — envelope is dishonest",
    );
  }

  return pass(
    "error_envelope",
    "bogus cursor → HTTP 400 JSON-RPC error {code:-32602, message:Invalid cursor} with no result payload",
  );
}

const CHECKERS: Record<GuaranteeId, (baseUrl: string) => Promise<GuaranteeResult>> = {
  completeness_honesty: checkCompletenessHonesty,
  cursor_validity: checkCursorValidity,
  keyset_stability: checkKeysetStability,
  revision_monotonicity: checkRevisionMonotonicity,
  client_id_idempotency: checkClientIdIdempotency,
  error_envelope: checkErrorEnvelope,
};

/** Run every live guarantee against baseUrl. Does not boot a server. */
export async function runLiveConformance(
  baseUrl: string = resolveConformanceBaseUrl(),
): Promise<LiveReport> {
  const probe = await probeLiveServer(baseUrl);
  if (!probe.ok) {
    return allGuaranteesSkipped(baseUrl, probe.reason);
  }

  const guarantees: GuaranteeResult[] = [];
  for (const id of GUARANTEE_IDS) {
    guarantees.push(await CHECKERS[id](baseUrl));
  }

  return {
    ok: liveReportOk(guarantees),
    skipped: false,
    skipReason: null,
    baseUrl,
    guarantees,
  };
}
