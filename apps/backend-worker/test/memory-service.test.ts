import { describe, expect, spyOn, test } from "bun:test";
import corpus from "../../../packages/contracts/ratified/fixtures/page-conformance.json";
import {
  MAX_CANONICAL_RESPONSE_BYTES,
  requestCanonicalService,
  type CanonicalCaller,
  type CanonicalService,
} from "../src/canonical-service";
import { readCanonicalMemoryPage } from "../src/memory-service";

const caller: CanonicalCaller = {
  accountId: "firebase:alice",
  authorization: "Bearer firebase-alice-test-token",
  stagingApiToken: "shared-staging-test-token",
};
const page = JSON.stringify(corpus[0]!.page).replace(
  "Synthesized result",
  "实际知识 🌍"
);
const serviceReturning = (
  body: string | Uint8Array,
  status = 200,
  headers: HeadersInit = { "content-type": "application/json" }
): CanonicalService => ({
  fetch: async () => new Response(body, { status, headers }),
});

describe("canonical memory service boundary", () => {
  test("forwards only the original verified Firebase bearer and preserves canonical bytes", async () => {
    let forwarded: Request | undefined;
    const service: CanonicalService = {
      fetch: async (request) => {
        forwarded = request;
        return new Response(page, {
          headers: {
            "content-type": "application/json",
            "set-cookie": "upstream-private=never-forward",
            "x-owner-id": "must-not-leak",
          },
        });
      },
    };
    const result = await readCanonicalMemoryPage({
      service,
      caller,
      query: new URLSearchParams({ limit: "7", cursor: "opaque+/cursor=" }),
      contractVersion: "1.0.0",
    });
    expect(forwarded?.url).toBe(
      "https://canonical.omi.internal/v1/memories?limit=7&cursor=opaque%2B%2Fcursor%3D"
    );
    expect(forwarded?.redirect).toBe("manual");
    expect([...forwarded!.headers]).toEqual([
      ["accept", "application/json"],
      ["authorization", caller.authorization!],
      ["x-omi-contract-version", "1.0.0"],
    ]);
    expect(result.kind).toBe("page");
    if (result.kind !== "page")
      throw new Error("Expected validated memory page");
    expect([...new Uint8Array(await result.response.arrayBuffer())]).toEqual([
      ...new TextEncoder().encode(page),
    ]);
    expect([...result.response.headers]).toEqual([
      ["cache-control", "no-store"],
      ["content-type", "application/json; charset=utf-8"],
    ]);
  });

  test("never lends shared staging credentials or a client-selected identity to the service", async () => {
    let calls = 0;
    const service: CanonicalService = {
      fetch: async () => {
        calls++;
        return new Response(page);
      },
    };
    for (const principal of [
      { ...caller, accountId: "staging-client-alice" },
      { ...caller, accountId: "firebase:" },
      { ...caller, authorization: `Bearer ${caller.stagingApiToken}` },
      { ...caller, authorization: undefined },
    ]) {
      expect(
        await readCanonicalMemoryPage({ service, caller: principal })
      ).toEqual({ kind: "unavailable" });
    }
    expect(calls).toBe(0);
  });

  test("upstream authorization follows the bearer, never a supplied account label", async () => {
    const seen: string[] = [];
    const service: CanonicalService = {
      fetch: async (request) => {
        seen.push(request.headers.get("authorization") ?? "");
        expect(request.headers.get("x-omi-client-id")).toBeNull();
        expect(request.headers.get("x-account-id")).toBeNull();
        return request.headers.get("authorization") === caller.authorization
          ? new Response(page, {
              headers: { "content-type": "application/json" },
            })
          : new Response('{"error":"forbidden"}', {
              status: 403,
              headers: { "content-type": "application/json" },
            });
      },
    };
    const result = await readCanonicalMemoryPage({
      service,
      caller: { ...caller, authorization: "Bearer firebase-bob-test-token" },
    });
    expect(result).toEqual({ kind: "denied", status: 403 });
    expect(seen).toEqual(["Bearer firebase-bob-test-token"]);
  });

  test("preserves every ratified safe completeness variant and rejects unsafe pages", async () => {
    for (const fixture of corpus) {
      const raw = JSON.stringify(fixture.page);
      const result = await readCanonicalMemoryPage({
        service: serviceReturning(raw),
        caller,
      });
      expect(result.kind).toBe(fixture.safe ? "page" : "unreadable");
      if (result.kind === "page")
        expect(await result.response.text()).toBe(raw);
    }
  });

  test("rejects duplicate keys, noncanonical encoding, BOM, malformed UTF-8 and legacy bodies", async () => {
    for (const raw of [
      page.replace(
        '{"contractVersion":',
        '{"contractVersion":"9.9.9","contractVersion":'
      ),
      ` ${page}`,
      '{"items":[],"complete":true}',
    ]) {
      expect(
        await readCanonicalMemoryPage({
          service: serviceReturning(raw),
          caller,
        })
      ).toEqual({ kind: "unreadable" });
    }
    for (const raw of [`\uFEFF${page}`, new Uint8Array([0xff, 0xfe])]) {
      expect(
        await readCanonicalMemoryPage({
          service: serviceReturning(raw),
          caller,
        })
      ).toEqual({ kind: "unavailable" });
    }
  });

  test("maps only standard typed denials and hides arbitrary upstream failures", async () => {
    for (const [status, error] of [
      [400, "bad_request"],
      [401, "unauthorized"],
      [403, "forbidden"],
    ] as const) {
      expect(
        await readCanonicalMemoryPage({
          service: serviceReturning(JSON.stringify({ error }), status),
          caller,
        })
      ).toEqual({ kind: "denied", status });
    }
    for (const status of [200, 401, 403, 500, 503]) {
      expect(
        await readCanonicalMemoryPage({
          service: serviceReturning(
            '{"error":"private-database-details"}',
            status
          ),
          caller,
        })
      ).toEqual({
        kind: status === 200 ? "unreadable" : "unavailable",
      });
    }
    expect(
      await readCanonicalMemoryPage({
        service: serviceReturning('{"error":"internal_server_error"}', 500),
        caller,
      })
    ).toEqual({ kind: "internal" });
    expect(
      await readCanonicalMemoryPage({ service: undefined, caller })
    ).toEqual({ kind: "unbound" });
    expect(
      await readCanonicalMemoryPage({
        service: {
          fetch: async () => {
            throw new Error("private transport detail");
          },
        },
        caller,
      })
    ).toEqual({ kind: "unavailable" });
  });

  test("rejects redirect responses and cancels oversized response streams", async () => {
    expect(
      await readCanonicalMemoryPage({
        service: serviceReturning("", 302, {
          location: "https://other.invalid/steal",
        }),
        caller,
      })
    ).toEqual({ kind: "unavailable" });
    let cancelled = false;
    const service: CanonicalService = {
      fetch: async () =>
        new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(
                new Uint8Array(MAX_CANONICAL_RESPONSE_BYTES + 1)
              );
            },
            cancel() {
              cancelled = true;
            },
          }),
          { headers: { "content-type": "application/json" } }
        ),
    };
    expect(await readCanonicalMemoryPage({ service, caller })).toEqual({
      kind: "unavailable",
    });
    expect(cancelled).toBe(true);
  });

  test("does not forward arbitrary paths, query authority, or GET request bodies", async () => {
    let calls = 0;
    const service: CanonicalService = {
      fetch: async () => {
        calls++;
        return new Response(page);
      },
    };
    for (const invalid of [
      { path: "/v1/private" as "/v1/memories" },
      { query: new URLSearchParams({ accountId: "victim" }) },
      { query: new URLSearchParams("limit=1&limit=2") },
      { body: "unexpected" },
    ]) {
      expect(
        await requestCanonicalService({
          service,
          caller,
          path: "/v1/memories",
          method: "GET",
          ...invalid,
        })
      ).toEqual({ kind: "unavailable" });
    }
    expect(calls).toBe(0);
  });
  test("cancels a delayed binding response after the request deadline already elapsed", async () => {
    let finishFetch!: (response: Response) => void;
    let finishCancel!: () => void;
    const cancelled = new Promise<void>((resolve) => {
      finishCancel = resolve;
    });
    const service: CanonicalService = {
      fetch: () =>
        new Promise<Response>((resolve) => {
          finishFetch = resolve;
        }),
    };
    const timer = spyOn(globalThis, "setTimeout").mockImplementationOnce(((
      callback: () => void
    ) => {
      queueMicrotask(callback);
      return 0;
    }) as unknown as typeof setTimeout);
    try {
      expect(await readCanonicalMemoryPage({ service, caller })).toEqual({
        kind: "unavailable",
      });
    } finally {
      timer.mockRestore();
    }
    let reads = 0;
    finishFetch(
      new Response(
        new ReadableStream(
          {
            pull() {
              reads++;
            },
            cancel() {
              finishCancel();
            },
          },
          { highWaterMark: 0 }
        ),
        { headers: { "content-type": "application/json" } }
      )
    );
    await cancelled;
    expect(reads).toBe(0);
  }, 1000);
});
