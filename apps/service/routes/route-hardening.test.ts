// domain-pending(DIV-DOMCORE-001)
// domain-pending(DIV-DOMAPPS-001)
// domain-pending(DIV-DOMAPPS-006)
import { Database } from "bun:sqlite";
import { describe, expect, test } from "bun:test";

import { parseSynthesizedPageJson } from "@omi-core/ratified-contracts/projections/synthesized";

import { createLocalDevService } from "../app-facing";

/**
 * Adversarial route-hardening for `GET /v1/memories`.
 *
 * Boots THE REAL SERVICE via `createLocalService` (same factory as
 * `bin/dev-server.ts`), hermetic and in-process: in-memory SQLite, no socket.
 * Failure bodies must stay FIXED constants with no leaked detail.
 */

const DEV_KEY_MATERIAL_LABEL = "omi-local-dev-token-not-a-secret-v1";
const OTHER_DEV_KEY_MATERIAL_LABEL = "omi-local-dev-token-other-instance-v2";
const OWNER_ACCOUNT_ID = "local-dev-user";
const MEMORY_COUNT = 6;
const ACCOUNT_TIMEZONE = "America/Los_Angeles";
const PAGE_LIMIT = 2;

const UNAUTHORIZED_BODY = '{"error":"unauthorized"}';
const BAD_REQUEST_BODY = '{"error":"bad_request"}';
const NOT_FOUND_BODY = '{"error":"not_found"}';

const LEAK_SUBSTRINGS = Object.freeze([
  "denied",
  "grant",
  "scope",
  "credential",
  "owner",
  "sqlite",
  "Error",
  "stack",
  "at ",
  OWNER_ACCOUNT_ID,
] as const);

const HEX_64 = /[0-9a-fA-F]{64}/;

interface BootedService {
  readonly fetch: (request: Request) => Response | Promise<Response>;
  readonly authorizationHeader: string;
  readonly devToken: string;
}

interface Captured {
  readonly status: number;
  readonly body: string;
}

/**
 * A Fetch `Headers` / `Request` constructor rejects CR, LF, and NUL in header
 * values before the app sees them. The route's `bearerToken` still receives
 * whatever string `req.header("authorization")` returns, so these cases drive
 * Hono through a Request-shaped stand-in whose `headers.get` returns the
 * forbidden bytes verbatim.
 */
const requestWithRawAuthorization = (authorization: string): Request => {
  const standIn = {
    method: "GET",
    url: "http://route-hardening.invalid/v1/memories",
    headers: {
      get(name: string): string | null {
        return name.toLowerCase() === "authorization" ? authorization : null;
      },
    },
  };
  return standIn as unknown as Request;
};

const bootService = (devSecretLabel: string = DEV_KEY_MATERIAL_LABEL): BootedService => {
  const service = createLocalDevService({
    db: new Database(":memory:"),
    ownerAccountId: OWNER_ACCOUNT_ID,
    memoryCount: MEMORY_COUNT,
    accountTimezone: ACCOUNT_TIMEZONE,
    devSecretLabel,
  });
  return Object.freeze({
    fetch: (request: Request) => service.app.fetch(request),
    authorizationHeader: `Bearer ${service.devToken}`,
    devToken: service.devToken,
  });
};

const memoriesUrl = (query: string = ""): string =>
  `http://route-hardening.invalid/v1/memories${query}`;

const capture = async (
  service: BootedService,
  request: Request,
): Promise<Captured> => {
  const response = await service.fetch(request);
  return Object.freeze({
    status: response.status,
    body: await response.text(),
  });
};

const getAuthorized = async (
  service: BootedService,
  query: string,
): Promise<Captured> =>
  capture(service, new Request(memoriesUrl(query), {
    method: "GET",
    headers: { authorization: service.authorizationHeader },
  }));

const assertNoLeak = (body: string): void => {
  for (const needle of LEAK_SUBSTRINGS) {
    expect(body.includes(needle)).toBe(false);
  }
  expect(HEX_64.test(body)).toBe(false);
};

const assertIdenticalFailures = (captured: readonly Captured[]): void => {
  expect(captured.length).toBeGreaterThan(1);
  const [first, ...rest] = captured;
  if (first === undefined) throw new Error("expected at least one captured response");
  for (const next of rest) {
    expect(next.status).toBe(first.status);
    expect(next.body).toBe(first.body);
  }
};

describe("route hardening: malformed Authorization", () => {
  const service = bootService();

  test("every malformed Authorization case is 401 with identical fixed unauthorized body", async () => {
    // red-proof: return distinct 401 bodies (or 403/500) per malformed-header
    // subclass so an attacker learns which part of Authorization failed.
    const cases: ReadonlyArray<{ readonly label: string; readonly request: Request }> = [
      {
        label: "missing header",
        request: new Request(memoriesUrl(), { method: "GET" }),
      },
      {
        label: "Bearer with no token",
        request: new Request(memoriesUrl(), {
          method: "GET",
          headers: { authorization: "Bearer" },
        }),
      },
      {
        label: "bearer lowercase prefix",
        request: new Request(memoriesUrl(), {
          method: "GET",
          headers: { authorization: `bearer ${service.devToken}` },
        }),
      },
      {
        label: "Basic scheme",
        request: new Request(memoriesUrl(), {
          method: "GET",
          headers: { authorization: "Basic xyz" },
        }),
      },
      {
        label: "Bearer plus 10000 chars",
        request: new Request(memoriesUrl(), {
          method: "GET",
          headers: { authorization: `Bearer ${"a".repeat(10_000)}` },
        }),
      },
      {
        label: "Authorization with CRLF",
        request: requestWithRawAuthorization("Bearer tok\r\ninjected"),
      },
      {
        label: "Authorization with null byte",
        request: requestWithRawAuthorization("Bearer tok\0x"),
      },
    ];

    const captured: Captured[] = [];
    for (const { request } of cases) {
      const result = await capture(service, request);
      expect(result.status).toBe(401);
      expect(result.body).toBe(UNAUTHORIZED_BODY);
      captured.push(result);
    }
    assertIdenticalFailures(captured);
    for (const result of captured) assertNoLeak(result.body);
  });
});

describe("route hardening: limit parameter abuse", () => {
  const service = bootService();

  test("abusive limit values are 400 with identical fixed bad_request body", async () => {
    // red-proof: accept limit=0/-1/101/non-digits or echo the raw limit into
    // the error body so clients (and attackers) learn the validation rule.
    const abusiveQueries = Object.freeze([
      "?limit=0",
      "?limit=-1",
      "?limit=101",
      "?limit=abc",
      "?limit=1e3",
      "?limit=999999999999999999999",
      "?limit=",
      "?limit=1.5",
    ] as const);

    const captured: Captured[] = [];
    for (const query of abusiveQueries) {
      const result = await getAuthorized(service, query);
      expect(result.status).toBe(400);
      expect(result.body).toBe(BAD_REQUEST_BODY);
      captured.push(result);
    }
    assertIdenticalFailures(captured);
    for (const result of captured) assertNoLeak(result.body);
  });

  test("limit omitted entirely uses the default and returns 200", async () => {
    // red-proof: require limit as mandatory so omitting it yields 400.
    const result = await getAuthorized(service, "");
    expect(result.status).toBe(200);
  });

  test("a repeated single-valued parameter fails closed, in either order", async () => {
    // This test previously documented Hono's first-wins behaviour, which was a
    // parameter-pollution bug: ?limit=5&limit=101 was answered 200 while
    // ?limit=101&limit=5 was answered 400, so two requests carrying the SAME
    // pair of values disagreed purely on ordering. `limit` and `cursor` are both
    // single-valued grammars, so ambiguity now fails closed rather than being
    // silently resolved.
    //
    // red-proof: delete the hasDuplicateQueryParameters check and the first
    // assertion below returns 200 again, restoring the order-dependence.
    for (const query of ["?limit=5&limit=101", "?limit=101&limit=5", "?cursor=a&cursor=b"]) {
      const result = await getAuthorized(service, query);
      expect(result.status).toBe(400);
      expect(result.body).toBe(BAD_REQUEST_BODY);
      assertNoLeak(result.body);
    }
  });

  test("duplicate rejection does not disturb the single-valued happy path", async () => {
    // red-proof: reject on any occurrence rather than on more than one, and a
    // perfectly ordinary ?limit=5 starts failing.
    const result = await getAuthorized(service, "?limit=5");
    expect(result.status).toBe(200);
    const parsed = parseSynthesizedPageJson(result.body);
    expect(parsed).not.toBeNull();
    if (parsed === null) throw new Error("expected synthesized page");
    expect(parsed.items.length).toBe(5);
  });
});

describe("route hardening: cursor abuse", () => {
  const service = bootService();
  const other = bootService(OTHER_DEV_KEY_MATERIAL_LABEL);

  test("empty cursor is treated as no cursor and returns 200", async () => {
    // red-proof: reject cursor= (empty) as invalid instead of coalescing to null.
    const emptyCursor = await getAuthorized(service, "?cursor=");
    const omitted = await getAuthorized(service, "");
    expect(emptyCursor.status).toBe(200);
    expect(omitted.status).toBe(200);
    expect(emptyCursor.body).toBe(omitted.body);
  });

  test("invalid cursors all produce the same status and byte-identical body", async () => {
    // red-proof: return distinct bodies/statuses for garbage vs bad-signature vs
    // foreign-instance cursors so rejection reason becomes an oracle.
    const firstPage = await getAuthorized(service, `?limit=${PAGE_LIMIT}`);
    expect(firstPage.status).toBe(200);
    const parsed = parseSynthesizedPageJson(firstPage.body);
    expect(parsed).not.toBeNull();
    if (parsed === null) throw new Error("expected synthesized page");
    const goodCursor = parsed.window.nextCursor;
    expect(typeof goodCursor).toBe("string");
    if (typeof goodCursor !== "string") throw new Error("expected nextCursor");

    const signatureTail = goodCursor.slice(-8);
    const flippedTail = signatureTail === "AAAAAAAA" ? "BBBBBBBB" : "AAAAAAAA";
    const badSignature = `${goodCursor.slice(0, -8)}${flippedTail}`;

    const otherFirst = await getAuthorized(other, `?limit=${PAGE_LIMIT}`);
    expect(otherFirst.status).toBe(200);
    const otherParsed = parseSynthesizedPageJson(otherFirst.body);
    expect(otherParsed).not.toBeNull();
    if (otherParsed === null) throw new Error("expected other synthesized page");
    const foreignCursor = otherParsed.window.nextCursor;
    expect(typeof foreignCursor).toBe("string");
    if (typeof foreignCursor !== "string") throw new Error("expected foreign nextCursor");

    const invalidCursors = Object.freeze([
      "garbage",
      badSignature,
      foreignCursor,
      // A REAL DEFECT this list did not reach until the two read-door
      // compositions were collapsed. The read core caps a cursor at 4096 code
      // units and rejects non-printable bytes with a plain `TypeError`, which
      // this route reports as 500 internal_server_error — while every other
      // cursor rejection above answers 400. Measured before the fix: a
      // 4096-character cursor answered 400, a 4097-character one answered 500.
      // Two mutations of one token producing two public outcomes tells an
      // attacker which half of their guess was wrong.
      //
      // The MCP door had already closed this with a syntactic pre-check in its
      // OWN composition; the REST door had not, because it had a different one.
      // The check now lives in the single shared `readMemoryPage`.
      //
      // red-proof: delete the `isSyntacticallyRedeemableCursor` guard from
      // `readMemoryPage` in apps/service/composition/memory-read.ts and these
      // two rows return 500 while the three above still return 400.
      "x".repeat(4_097),
      "a\u0001b",
    ] as const);

    const captured: Captured[] = [];
    for (const cursor of invalidCursors) {
      const result = await getAuthorized(
        service,
        `?limit=${PAGE_LIMIT}&cursor=${encodeURIComponent(cursor)}`,
      );
      expect(result.status).toBe(400);
      expect(result.body).toBe(BAD_REQUEST_BODY);
      captured.push(result);
    }
    assertIdenticalFailures(captured);
    expect(captured[0]!.body).toBe(captured[1]!.body);
    expect(captured[1]!.body).toBe(captured[2]!.body);
    for (const result of captured) assertNoLeak(result.body);
  });
});

describe("route hardening: method and path", () => {
  const service = bootService();

  test("POST /v1/memories is not 200 and returns the fixed not_found body", async () => {
    // red-proof: accept POST on the memory read path (status 200) or leak a
    // method-not-allowed detail body instead of the fixed not_found constant.
    const result = await capture(service, new Request(memoriesUrl(), {
      method: "POST",
      headers: { authorization: service.authorizationHeader },
    }));
    expect(result.status).not.toBe(200);
    expect(result.status).toBe(404);
    expect(result.body).toBe(NOT_FOUND_BODY);
    assertNoLeak(result.body);
  });

  test("GET /v1/memories/ trailing slash is 404 with fixed not_found body", async () => {
    // red-proof: register a non-strict trailing-slash alias so /v1/memories/
    // serves 200 instead of the fixed 404 not_found body.
    const result = await capture(service, new Request(
      "http://route-hardening.invalid/v1/memories/",
      { method: "GET", headers: { authorization: service.authorizationHeader } },
    ));
    expect(result.status).toBe(404);
    expect(result.body).toBe(NOT_FOUND_BODY);
    assertNoLeak(result.body);
  });

  test("GET /v1/nonexistent is 404 with fixed not_found body", async () => {
    // red-proof: return a path-echoing or stack-bearing 404 body instead of the
    // fixed {"error":"not_found"} constant.
    const result = await capture(service, new Request(
      "http://route-hardening.invalid/v1/nonexistent",
      { method: "GET", headers: { authorization: service.authorizationHeader } },
    ));
    expect(result.status).toBe(404);
    expect(result.body).toBe(NOT_FOUND_BODY);
    assertNoLeak(result.body);
  });
});

describe("route hardening: no detail leakage across failing cases", () => {
  const service = bootService();

  test("no failing body contains denial vocabulary, owner id, or 64-char hex", async () => {
    // red-proof: interpolate ApplicationReadDenied reason, exception.message,
    // stack frames, owner id, or digest hex into any failure body above.
    const failing: Captured[] = [
      await capture(service, new Request(memoriesUrl(), { method: "GET" })),
      await capture(service, new Request(memoriesUrl(), {
        method: "GET",
        headers: { authorization: "Basic xyz" },
      })),
      await capture(service, requestWithRawAuthorization("Bearer tok\r\ninjected")),
      await capture(service, requestWithRawAuthorization("Bearer tok\0x")),
      await getAuthorized(service, "?limit=0"),
      await getAuthorized(service, "?limit=abc"),
      await getAuthorized(service, "?limit=101&limit=5"),
      await getAuthorized(service, "?cursor=garbage"),
      await capture(service, new Request(memoriesUrl(), {
        method: "POST",
        headers: { authorization: service.authorizationHeader },
      })),
      await capture(service, new Request(
        "http://route-hardening.invalid/v1/memories/",
        { method: "GET", headers: { authorization: service.authorizationHeader } },
      )),
      await capture(service, new Request(
        "http://route-hardening.invalid/v1/nonexistent",
        { method: "GET" },
      )),
    ];

    for (const result of failing) {
      expect(result.status).not.toBe(200);
      assertNoLeak(result.body);
    }
  });
});
