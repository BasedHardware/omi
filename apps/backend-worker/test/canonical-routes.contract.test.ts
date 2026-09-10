import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  mock,
  test,
} from "bun:test";
import memoryCorpus from "../../../packages/contracts/ratified/fixtures/page-conformance.json";
import taskCorpus from "../../../packages/contracts/ratified/fixtures/tasks-read-conformance.json";
import type { CanonicalService } from "../src/canonical-service";

let worker: typeof import("../src/index")["default"];
const originalFetch = globalThis.fetch;
let verifierCalls = 0;
let d1Reads = 0;
const memoryPage = JSON.stringify(memoryCorpus[0]!.page);
const taskPage = JSON.stringify({ ...taskCorpus[0]!.page, accountEpoch: 7 });
const rawWrite = `{
  "write_id": "${"a".repeat(64)}",
  "account_epoch": 7,
  "domain": "tasks",
  "op": { "op": "create", "record_id": "task-1", "content": { "title": "keep  spaces" } }
}\n`;
const accepted =
  '{"applied":{"record_id":"task-1","revision":null},"idempotent":false}';
const executionContext = {
  waitUntil: (_promise: Promise<unknown>) => undefined,
  passThroughOnException: () => undefined,
  props: {},
};
const env = {
  ENVIRONMENT: "test",
  API_TOKEN: "route-test-staging",
  FIREBASE_API_KEY: "route-test-firebase-key",
  STAGING_ACCOUNT_ID: "test-account",
  STAGING_CHAT_LIMIT: 1,
  AI_MODEL: "test-model",
  AI: {},
  ACCOUNTS: {},
  DB: {
    prepare() {
      d1Reads += 1;
      throw new Error("Canonical paths must not read D1");
    },
  },
  OBSERVABILITY_SINK_MODE: "cloudflare_only",
  OPENROUTER_GATEWAY_ENABLED: "false",
};

beforeAll(async () => {
  void mock.module("cloudflare:workers", () => ({ DurableObject: class {} }));
  worker = (await import("../src/index")).default;
});
beforeEach(() => {
  verifierCalls = 0;
  d1Reads = 0;
  globalThis.fetch = mock(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const request = new Request(input, init);
      expect(request.url).toBe(
        "https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=route-test-firebase-key"
      );
      expect((await request.json()) as unknown).toEqual({
        idToken: "route-test-firebase-token",
      });
      verifierCalls += 1;
      return Response.json({ users: [{ localId: "route-user" }] });
    }
  ) as unknown as typeof fetch;
});
afterEach(() => {
  globalThis.fetch = originalFetch;
});

function request(
  path: string,
  service?: CanonicalService,
  staging = false,
  method = "GET",
  body?: string
) {
  return worker.fetch(
    new Request(`https://worker.test${path}`, {
      method,
      headers: {
        authorization: `Bearer ${
          staging ? env.API_TOKEN : "route-test-firebase-token"
        }`,
        "x-omi-client-id": "spoofed-client-account",
        "x-omi-contract-version": "1.0.0",
        "content-type": "application/json",
      },
      ...(body === undefined ? {} : { body }),
    }),
    {
      ...env,
      ...(service === undefined ? {} : { CANONICAL_SERVICE: service }),
    } as never,
    executionContext as never
  );
}

describe("registered canonical routes", () => {
  test("unauthenticated writes never reach the canonical service", async () => {
    let calls = 0;
    const response = await worker.fetch(
      new Request("https://worker.test/v1/tasks/ops", {
        method: "POST",
        body: rawWrite,
      }),
      {
        ...env,
        CANONICAL_SERVICE: {
          async fetch() {
            calls += 1;
            return new Response(accepted);
          },
        },
      } as never,
      executionContext as never
    );
    expect(response.status).toBe(401);
    expect(calls).toBe(0);
    expect(verifierCalls).toBe(0);
    expect(d1Reads).toBe(0);
  });

  test.each([
    {
      path: "/v1/tasks?limit=7&cursor=opaque%2B%2Fcursor%3D",
      response: taskPage,
    },
    {
      path: "/v1/memories?limit=7&cursor=opaque%2B%2Fcursor%3D",
      response: memoryPage,
    },
  ])(
    "Firebase auth precedes binding and exact read bytes survive: $path",
    async (entry) => {
      let forwarded: Request | undefined;
      const response = await request(entry.path, {
        async fetch(input) {
          expect(verifierCalls).toBe(1);
          forwarded = input;
          return new Response(entry.response, {
            headers: { "content-type": "application/json" },
          });
        },
      });
      expect(response.status).toBe(200);
      expect(await response.text()).toBe(entry.response);
      expect(forwarded?.url).toBe(
        `https://canonical.omi.internal${entry.path}`
      );
      expect([...forwarded!.headers]).toEqual([
        ["accept", "application/json"],
        ["authorization", "Bearer route-test-firebase-token"],
        ["x-omi-contract-version", "1.0.0"],
      ]);
      expect(d1Reads).toBe(0);
    }
  );

  test("task write forwards original whitespace, epoch and bearer without serialization", async () => {
    let forwarded: Request | undefined;
    const response = await request(
      "/v1/tasks/ops",
      {
        async fetch(input) {
          expect(verifierCalls).toBe(1);
          forwarded = input;
          return new Response(accepted, {
            headers: { "content-type": "application/json" },
          });
        },
      },
      false,
      "POST",
      rawWrite
    );
    expect(response.status).toBe(200);
    expect(await response.text()).toBe(accepted);
    expect(forwarded?.method).toBe("POST");
    expect(await forwarded!.text()).toBe(rawWrite);
    expect(forwarded?.headers.get("authorization")).toBe(
      "Bearer route-test-firebase-token"
    );
    expect(forwarded?.headers.has("x-omi-client-id")).toBe(false);
    expect(d1Reads).toBe(0);
  });

  test.each(["/v1/tasks", "/v1/tasks/ops", "/v1/memories"])(
    "staging bearer never reaches canonical authority: %s",
    async (path) => {
      let calls = 0;
      const response = await request(
        path,
        {
          async fetch() {
            calls += 1;
            throw new Error("Staging token must not be delegated");
          },
        },
        true,
        path.endsWith("/ops") ? "POST" : "GET",
        path.endsWith("/ops") ? rawWrite : undefined
      );
      expect(response.status).toBe(503);
      expect(calls).toBe(0);
      expect(verifierCalls).toBe(0);
      expect(d1Reads).toBe(0);
    }
  );

  test("absent binding refuses writes, configured unavailable tasks never fall back to D1", async () => {
    const write = await request(
      "/v1/tasks/ops",
      undefined,
      false,
      "POST",
      rawWrite
    );
    expect(write.status).toBe(503);
    expect(await write.text()).toBe(
      '{"error":"maintenance","refusal_outcome":"control_unavailable"}'
    );
    const read = await request("/v1/tasks", {
      async fetch() {
        throw new Error("Authority unavailable");
      },
    });
    expect(read.status).toBe(503);
    expect(read.headers.get("retry-after")).not.toBeNull();
    expect(await read.text()).toBe('{"error":"internal_server_error"}');
    expect(d1Reads).toBe(0);
  });

  test("canonical memory INTERNAL 500 is not rewritten to retryable projection_unavailable", async () => {
    const response = await request("/v1/memories", {
      async fetch() {
        return new Response('{"error":"internal_server_error"}', {
          status: 500,
          headers: { "content-type": "application/json" },
        });
      },
    });
    expect(response.status).toBe(500);
    expect(response.headers.get("retry-after")).toBeNull();
    expect((await response.json()) as unknown).toEqual({
      error: "internal_server_error",
    });
    expect(d1Reads).toBe(0);
  });

  test("unreadable canonical task pages are non-retryable and never fall back to D1", async () => {
    const response = await request("/v1/tasks", {
      async fetch() {
        return new Response('{"items":[]}', {
          headers: { "content-type": "application/json" },
        });
      },
    });
    expect(response.status).toBe(503);
    expect(response.headers.get("retry-after")).toBeNull();
    expect((await response.json()) as unknown).toEqual({
      error: {
        code: "projection_unavailable",
        retryable: false,
        action: "none",
      },
    });
    expect(d1Reads).toBe(0);
  });
});
