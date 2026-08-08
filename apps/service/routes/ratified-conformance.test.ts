// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMCORE-006)
// domain-pending(DIV-DOMCORE-008)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { parseKeysetCursor } from "@omi-core/ratified-contracts/pagination/cursor";
import {
  SYNTHESIZED_READ_CONTRACT_VERSION,
  isTrustedPageWindowHonest,
  isTrustedRecallCompletenessHonest,
  isTrustedSynthesizedPageData,
  parseSynthesizedPageJson,
} from "@omi-core/ratified-contracts/projections/synthesized";

import { createLocalService } from "../app-facing";

/**
 * Proves the bytes `/v1/memories` emits satisfy the RATIFIED synthesized-read
 * contract, judged only by the ratified package parsers and honesty predicates.
 *
 * Boot wiring mirrors `apps/service/bin/dev-server.ts` (seed + loader + auth +
 * composition) but stays hermetic: in-memory SQLite, no socket.
 */

const DEV_KEY_MATERIAL_LABEL = "omi-local-dev-token-not-a-secret-v1";
const OWNER_ACCOUNT_ID = "local-dev-user";
const MEMORY_COUNT = 6;
const ACCOUNT_TIMEZONE = "America/Los_Angeles";
const PAGE_LIMIT = 2;
const MAX_PAGES = 64;

/** Legacy editable-memory fields and internal IDs that must never appear as object keys. */
const FORBIDDEN_OBJECT_KEYS = Object.freeze([
  "content",
  "locked",
  "visibility",
  "category",
  "review",
  "reviewed",
  "transcript",
  "tags",
  "tier",
  "layer",
  "cohort",
  "store",
  "appId",
  "app",
  "ownerId",
  "owner",
  "key",
  "summary",
  "displayOrder",
  "order",
  "stale",
  "failure",
  "accountGeneration",
  "ownerGeneration",
  "projectionGeneration",
  "graphGeneration",
  "commitId",
  "frontierId",
  "renderManifest",
  "policyLabel",
  "policyClass",
  "evidence",
  "raw",
  "excerpt",
] as const);

const FORBIDDEN_KEY_SET = new Set<string>(FORBIDDEN_OBJECT_KEYS);

const RAW_EVIDENCE_SUBSTRING = "qa memory";

interface BootedService {
  readonly fetch: (request: Request) => Response | Promise<Response>;
  readonly authorizationHeader: string;
}

/**
 * Boots THE REAL SERVICE, not a lookalike.
 *
 * This deliberately goes through `createLocalService` - the exact factory
 * `bin/dev-server.ts` uses - rather than re-assembling seed + loader + auth +
 * composition here. A test that builds its own wiring can agree perfectly with
 * itself while the shipped binding is wrong, which is how a green hermetic
 * suite once accompanied a bridge that served zero requests. The only
 * difference from the dev server is that this binds no socket.
 */
const bootService = (): BootedService => {
  const service = createLocalService({
    db: new Database(":memory:"),
    ownerAccountId: OWNER_ACCOUNT_ID,
    memoryCount: MEMORY_COUNT,
    accountTimezone: ACCOUNT_TIMEZONE,
    devSecretLabel: DEV_KEY_MATERIAL_LABEL,
  });

  return Object.freeze({
    fetch: (request: Request) => service.app.fetch(request),
    authorizationHeader: `Bearer ${service.devToken}`,
  });
};

const memoriesUrl = (limit: number, cursor: string | null): string => {
  const url = new URL("http://ratified-conformance.invalid/v1/memories");
  url.searchParams.set("limit", String(limit));
  if (cursor !== null) url.searchParams.set("cursor", cursor);
  return url.toString();
};

const fetchPageBody = async (
  service: BootedService,
  cursor: string | null,
  limit: number = PAGE_LIMIT,
): Promise<string> => {
  const response = await service.fetch(new Request(memoriesUrl(limit, cursor), {
    method: "GET",
    headers: { authorization: service.authorizationHeader },
  }));
  expect(response.status).toBe(200);
  expect(response.headers.get("content-type")).toBe("application/json");
  return await response.text();
};

interface WalkedPage {
  readonly rawBody: string;
  readonly page: NonNullable<ReturnType<typeof parseSynthesizedPageJson>>;
}

const walkAllPages = async (service: BootedService): Promise<readonly WalkedPage[]> => {
  const walked: WalkedPage[] = [];
  let cursor: string | null = null;
  for (let pageIndex = 0; pageIndex < MAX_PAGES; pageIndex += 1) {
    const rawBody = await fetchPageBody(service, cursor);
    const page = parseSynthesizedPageJson(rawBody);
    expect(page).not.toBeNull();
    if (page === null) throw new Error("parseSynthesizedPageJson returned null");
    walked.push({ rawBody, page });
    if (!page.window.hasMore) {
      expect(page.window.nextCursor).toBeNull();
      return walked;
    }
    expect(page.window.nextCursor).not.toBeNull();
    cursor = page.window.nextCursor;
  }
  throw new Error(`pagination did not terminate within ${MAX_PAGES} pages`);
};

const collectForbiddenKeys = (value: unknown, path: string, hits: string[]): void => {
  if (value === null || typeof value !== "object") return;
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      collectForbiddenKeys(value[index], `${path}[${index}]`, hits);
    }
    return;
  }
  const record = value as Record<string, unknown>;
  for (const key of Object.keys(record)) {
    if (FORBIDDEN_KEY_SET.has(key)) hits.push(`${path}.${key}`);
    collectForbiddenKeys(record[key], `${path}.${key}`, hits);
  }
};

const stripOptionalItemFields = (
  page: NonNullable<ReturnType<typeof parseSynthesizedPageJson>>,
): unknown => {
  const clone = structuredClone(page) as {
    items: Array<Record<string, unknown>>;
    [key: string]: unknown;
  };
  for (const item of clone.items) {
    delete item["citations"];
    delete item["provenance"];
  }
  return clone;
};

describe("ratified synthesized page wire conformance", () => {
  const service = bootService();

  test("every walked page is accepted by the ratified wire parsers and honesty predicates", async () => {
    // red-proof: emit pretty-printed / non-canonical JSON, wrong contractVersion,
    // dishonest window/completeness pairing, or an unparseable nextCursor so
    // parseSynthesizedPageJson / honesty predicates / parseKeysetCursor fail.
    const pages = await walkAllPages(service);
    expect(pages.length).toBeGreaterThan(0);

    for (const { rawBody, page } of pages) {
      expect(parseSynthesizedPageJson(rawBody)).not.toBeNull();
      expect(isTrustedPageWindowHonest(page.window)).toBe(true);
      expect(isTrustedRecallCompletenessHonest(page)).toBe(true);
      expect(page.contractVersion).toBe(SYNTHESIZED_READ_CONTRACT_VERSION);
      if (page.window.nextCursor !== null) {
        expect(parseKeysetCursor(page.window.nextCursor)).not.toBeNull();
      }
    }
  });

  test("forbidden legacy and internal object keys never appear anywhere on a page", async () => {
    // red-proof: inject any forbidden key (e.g. excerpt, content, ownerId, commitId)
    // onto any nested object in the response graph.
    const pages = await walkAllPages(service);
    for (const { page } of pages) {
      const hits: string[] = [];
      collectForbiddenKeys(page, "$", hits);
      expect(hits).toEqual([]);
    }
  });

  test("raw seed evidence excerpt substring never appears in any page body", async () => {
    // red-proof: synthesize by passthrough of evidence.excerpt so the body
    // contains the seeder substring "qa memory".
    const pages = await walkAllPages(service);
    for (const { rawBody } of pages) {
      expect(rawBody.includes(RAW_EVIDENCE_SUBSTRING)).toBe(false);
    }
  });

  test("clients may ignore optional citations and provenance and remain correct", async () => {
    // red-proof: make citations or provenance required in the Item shape so
    // stripping them causes isTrustedSynthesizedPageData to reject.
    const pages = await walkAllPages(service);
    expect(pages.some(({ page }) => page.items.some((item) =>
      Object.prototype.hasOwnProperty.call(item, "citations")
      || Object.prototype.hasOwnProperty.call(item, "provenance")))).toBe(true);

    for (const { page } of pages) {
      if (page.items.length === 0) continue;
      const stripped = stripOptionalItemFields(page);
      expect(isTrustedSynthesizedPageData(stripped)).toBe(true);
    }
  });

  test("the same page request is byte-identical across two fetches", async () => {
    // red-proof: introduce non-determinism (wall clock, random ids, unstable
    // key order, or a mutating read) so two identical requests differ by a byte.
    const first = await fetchPageBody(service, null);
    const second = await fetchPageBody(service, null);
    expect(second).toBe(first);

    const firstPage = parseSynthesizedPageJson(first);
    expect(firstPage).not.toBeNull();
    if (firstPage === null) throw new Error("first page failed to parse");
    if (firstPage.window.nextCursor !== null) {
      const cursor = firstPage.window.nextCursor;
      const continuedA = await fetchPageBody(service, cursor);
      const continuedB = await fetchPageBody(service, cursor);
      expect(continuedB).toBe(continuedA);
    }
  });
});

describe("memory read path spelling", () => {
  const service = bootService();

  test("the transitional alias returns byte-identical responses to the canonical path", async () => {
    // red-proof: give the alias its own handler (or a different default limit)
    // and the bodies diverge. The alias exists only so FE-CORE is not broken
    // mid-flight; it must never become a second, subtly different endpoint.
    const request = (path: string) => new Request(
      `http://ratified-conformance.invalid${path}?limit=${PAGE_LIMIT}`,
      { method: "GET", headers: { authorization: service.authorizationHeader } },
    );

    const canonical = await service.fetch(request("/v1/memories"));
    const alias = await service.fetch(request("/v1/memories/recall"));

    expect(alias.status).toBe(canonical.status);
    expect(await alias.text()).toBe(await canonical.text());
  });

  test("an unknown sibling path is still a 404, so the alias is a route and not a prefix match", async () => {
    // red-proof: register the alias as a wildcard/prefix and this returns 200.
    const response = await service.fetch(new Request(
      "http://ratified-conformance.invalid/v1/memories/nonsense",
      { method: "GET", headers: { authorization: service.authorizationHeader } },
    ));
    expect(response.status).toBe(404);
  });
});
