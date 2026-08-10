/**
 * The bridge-HTTP seam: contract shapes -> the `HttpClient` answers the sync
 * layer already knows how to classify. This is the join between a new transport
 * and the existing failure taxonomy, so it is the part that can silently
 * regress: a wrong mapping here turns a paused queue into a retry-spin, or a
 * permanent rejection into an infinite retry.
 *
 * Hermetic: a fake reply-capable handler stands in for the shell. No network,
 * no webview, no real time.
 *
 * RED-PROOF (rule 14): change `not-authenticated` in
 * `BRIDGE_HTTP_FAILURE_STATUS` (contracts/src/bridge/http.ts) from 401 to 503
 * and "not-authenticated pauses the queue" fails; drop the `authorization`
 * entry from `BRIDGE_HTTP_FORBIDDEN_HEADERS` and the forbidden-header law fails.
 */

import assert from "node:assert/strict";
import { test } from "node:test";
import {
  BRIDGE_HTTP_CHANNEL,
  BRIDGE_HTTP_FAILURE_STATUS,
  BRIDGE_HTTP_FORBIDDEN_HEADERS,
  BRIDGE_HTTP_REPLY_FUNCTION,
  type BridgeHttpFailureReason,
  type BridgeHttpReply,
  type BridgeHttpRequest,
} from "@omi-core/contracts";
import { bridgeHttpClient, isBridgeHttpAvailable } from "@omi-core/bridge-web";
import { fetchPlatformSettings } from "@omi-core/adapters-platform";
import { classifyStatus } from "@omi-core/kernel";

/** Install a fake shell handler; returns the requests it saw. */
function installShell(reply: (req: BridgeHttpRequest) => BridgeHttpReply | Promise<BridgeHttpReply>): {
  seen: BridgeHttpRequest[];
  uninstall(): void;
} {
  const seen: BridgeHttpRequest[] = [];
  const g = globalThis as unknown as { webkit?: unknown };
  const previous = g.webkit;
  g.webkit = {
    messageHandlers: {
      [BRIDGE_HTTP_CHANNEL]: {
        async postMessage(msg: unknown): Promise<unknown> {
          const req = msg as BridgeHttpRequest;
          seen.push(req);
          return reply(req);
        },
      },
    },
  };
  return {
    seen,
    uninstall() {
      if (previous === undefined) delete g.webkit;
      else g.webkit = previous;
    },
  };
}

test("feature detection is false without a shell and true with one", async () => {
  const g = globalThis as unknown as { webkit?: unknown };
  delete g.webkit;
  assert.equal(isBridgeHttpAvailable(), false, "a plain browser must fall back to the dev transport");
  const shell = installShell(() => ({ ok: true, response: { id: "x", status: 200, body: "{}" } }));
  try {
    assert.equal(isBridgeHttpAvailable(), true);
  } finally {
    shell.uninstall();
  }
});

test("a real reply becomes an HttpResponse with a parsed body", async () => {
  const shell = installShell((req) => ({
    ok: true,
    response: { id: req.id, status: 200, body: JSON.stringify({ action_items: [1, 2] }) },
  }));
  try {
    const res = await bridgeHttpClient().request("GET", "/v1/action-items?limit=2");
    assert.equal(res.status, 200);
    assert.deepEqual(res.json, { action_items: [1, 2] });
    assert.equal(shell.seen[0]!.path, "/v1/action-items?limit=2", "the path crosses unchanged");
    assert.equal(shell.seen[0]!.method, "GET");
  } finally {
    shell.uninstall();
  }
});

test("a body is JSON-encoded once and the surface never sees a base URL", async () => {
  const shell = installShell((req) => ({ ok: true, response: { id: req.id, status: 201, body: null } }));
  try {
    const res = await bridgeHttpClient().request("POST", "/v1/folders", { name: "Work" });
    assert.equal(res.status, 201);
    assert.equal(res.json, null, "an empty body is null, matching the seam's contract");
    assert.equal(shell.seen[0]!.body, '{"name":"Work"}');
    // Nothing in the outgoing message may resemble an endpoint or credential.
    const wire = JSON.stringify(shell.seen[0]);
    assert.ok(!/https?:\/\//.test(wire), `no absolute URL may cross: ${wire}`);
    assert.ok(!/authorization|bearer/i.test(wire), `no credential may cross: ${wire}`);
  } finally {
    shell.uninstall();
  }
});

test("every transport failure maps onto the existing taxonomy, and none is unclassified", async () => {
  const reasons: BridgeHttpFailureReason[] = [
    "offline",
    "timeout",
    "cancelled",
    "shell-error",
    "not-authenticated",
  ];
  for (const reason of reasons) {
    const shell = installShell((req) => ({ ok: false, failure: { id: req.id, reason, detail: "x" } }));
    try {
      const res = await bridgeHttpClient().request("GET", "/v1/action-items");
      assert.equal(res.status, BRIDGE_HTTP_FAILURE_STATUS[reason], `${reason} status`);
      const failure = classifyStatus(res, reason);
      assert.notEqual(
        (failure as { unclassified?: boolean }).unclassified,
        true,
        `${reason} must not land in the unclassified bucket`,
      );
    } finally {
      shell.uninstall();
    }
  }
});

test("not-authenticated pauses the queue; other failures retry", async () => {
  const paused = classifyStatus(
    { status: BRIDGE_HTTP_FAILURE_STATUS["not-authenticated"], json: null },
    "no credential",
  );
  assert.equal(paused.kind, "auth-invalid", "the shell holding no credential must PAUSE, never retry-spin");
  for (const reason of ["offline", "timeout", "cancelled", "shell-error"] as BridgeHttpFailureReason[]) {
    const f = classifyStatus({ status: BRIDGE_HTTP_FAILURE_STATUS[reason], json: null }, reason);
    assert.equal(f.kind, "retryable", `${reason} must be retryable`);
  }
});

test("a server rejection stays a server status, distinct from a transport failure", async () => {
  const shell = installShell((req) => ({ ok: true, response: { id: req.id, status: 422, body: "{}" } }));
  try {
    const res = await bridgeHttpClient().request("POST", "/v1/action-items", { description: "x" });
    const f = classifyStatus(res, "create");
    assert.equal(f.kind, "permanent", "422 dead-letters rather than retrying forever");
    assert.equal((f as { reason: string }).reason, "validation");
  } finally {
    shell.uninstall();
  }
});

test("Settings consumes the bridge artifact's host reason without confusing a real 401", async () => {
  const absent = installShell((req) => ({
    ok: false,
    failure: { id: req.id, reason: "not-authenticated", detail: "shell holds no credential" },
  }));
  try {
    const outcome = await fetchPlatformSettings(bridgeHttpClient());
    assert.deepEqual(outcome, {
      kind: "snapshot",
      snapshot: { identity: null, entitlement: null },
    });
  } finally {
    absent.uninstall();
  }

  const invalid = installShell((req) => ({
    ok: true,
    response: { id: req.id, status: 401, body: '{"error":"unauthorized"}' },
  }));
  try {
    const outcome = await fetchPlatformSettings(bridgeHttpClient());
    assert.deepEqual(outcome, { kind: "auth-invalid", status: 401 });
    // red-proof: drop HttpResponse.transportFailureReason and make the adapter
    // infer signed-out from status 401; this real server rejection becomes the
    // same snapshot as the host failure above and this assertion fails.
  } finally {
    invalid.uninstall();
  }
});

test("retryAfterMs is carried through so rate limiting honors the server hint", async () => {
  const shell = installShell((req) => ({
    ok: true,
    response: { id: req.id, status: 429, body: "{}", retryAfterMs: 7000 },
  }));
  try {
    const res = await bridgeHttpClient().request("GET", "/v1/action-items");
    const f = classifyStatus(res, "list");
    assert.equal(f.kind, "rate-limited");
    assert.equal((f as { retryAfterMs: number }).retryAfterMs, 7000, "the hint must not be replaced by a default");
  } finally {
    shell.uninstall();
  }
});

test("a malformed or rejected reply degrades to retryable, never throws", async () => {
  for (const bad of [undefined, null, {}, { ok: true }, { ok: true, response: {} }, "nope"]) {
    const shell = installShell(() => bad as unknown as BridgeHttpReply);
    try {
      const res = await bridgeHttpClient().request("GET", "/v1/action-items");
      assert.equal(res.status, BRIDGE_HTTP_FAILURE_STATUS["shell-error"]);
      assert.equal(classifyStatus(res, "x").kind, "retryable");
    } finally {
      shell.uninstall();
    }
  }
  const throwing = installShell(() => {
    throw new Error("handler blew up");
  });
  try {
    const res = await bridgeHttpClient().request("GET", "/v1/action-items");
    assert.equal(res.status, BRIDGE_HTTP_FAILURE_STATUS["shell-error"], "a throwing shell is a transport failure");
  } finally {
    throwing.uninstall();
  }
});

test("the forbidden-header list names every credential-bearing header the shell must strip", () => {
  // The shell enforces this; the contract must not silently narrow it.
  for (const h of ["authorization", "cookie", "proxy-authorization"]) {
    assert.ok(
      (BRIDGE_HTTP_FORBIDDEN_HEADERS as readonly string[]).includes(h),
      `${h} must stay forbidden — the shell owns auth`,
    );
  }
  for (const h of BRIDGE_HTTP_FORBIDDEN_HEADERS) {
    assert.equal(h, h.toLowerCase(), "entries are lowercase for direct comparison after normalization");
  }
});

// ---------------------------------------------------------------------------
// Transport 2: ONE-WAY channel + reply function (iOS/Flutter, and the shape
// Android would use). The channel carries strings surface->shell only, so the
// shell delivers each reply by calling BRIDGE_HTTP_REPLY_FUNCTION with the
// request id. This is the transport that makes the contract's `id` load-bearing.
//
// RED-PROOF (rule 14):
//  - delete the `pending.delete(message.id)` + id lookup in installReplySink so
//    any reply resolves any request => "concurrent one-way requests" fails;
//  - remove the setTimeout guard in the one-way branch => "a lost reply" hangs
//    and fails by test timeout;
//  - re-add `(timer as unknown as { unref?: () => void }).unref?.()` in the
//    one-way branch => Node cancels the lost-reply test before its timeout can
//    settle, proving the timeout must stay referenced;
//  - reorder detectTransport to check the one-way channel first => "reply-capable
//    transport wins" fails.
// ---------------------------------------------------------------------------

/** Install a fake one-way channel; the shell replies via the global sink. */
function installOneWayShell(
  onRequest: (req: BridgeHttpRequest, reply: (r: BridgeHttpReply | string) => void) => void,
): { seen: BridgeHttpRequest[]; uninstall(): void } {
  const seen: BridgeHttpRequest[] = [];
  const g = globalThis as unknown as Record<string, unknown>;
  const prevWebkit = g["webkit"];
  const prevChannel = g[BRIDGE_HTTP_CHANNEL];
  delete g["webkit"]; // force one-way detection
  g[BRIDGE_HTTP_CHANNEL] = {
    postMessage(raw: string): void {
      const req = JSON.parse(raw) as BridgeHttpRequest;
      seen.push(req);
      const deliver = (r: BridgeHttpReply | string): void => {
        const sink = g[BRIDGE_HTTP_REPLY_FUNCTION] as (id: string, json: unknown) => void;
        sink(req.id, typeof r === "string" ? r : JSON.stringify(r));
      };
      onRequest(req, deliver);
    },
  };
  return {
    seen,
    uninstall() {
      if (prevWebkit === undefined) delete g["webkit"];
      else g["webkit"] = prevWebkit;
      if (prevChannel === undefined) delete g[BRIDGE_HTTP_CHANNEL];
      else g[BRIDGE_HTTP_CHANNEL] = prevChannel;
    },
  };
}

test("a one-way channel is detected and round-trips through the reply function", async () => {
  const shell = installOneWayShell((req, reply) =>
    reply({ ok: true, response: { id: req.id, status: 200, body: JSON.stringify({ saw: req.path }) } }),
  );
  try {
    assert.equal(isBridgeHttpAvailable(), true, "a one-way channel is a usable bridge");
    const res = await bridgeHttpClient().request("GET", "/v1/action-items");
    assert.equal(res.status, 200);
    assert.deepEqual(res.json, { saw: "/v1/action-items" });
    assert.equal(shell.seen.length, 1);
    // The channel carries a STRING; nothing about the endpoint or a credential.
    const wire = JSON.stringify(shell.seen[0]);
    assert.ok(!/https?:\/\//.test(wire) && !/authorization|bearer/i.test(wire), wire);
  } finally {
    shell.uninstall();
  }
});

test("concurrent one-way requests are correlated by id, not by arrival order", async () => {
  const deferred: { req: BridgeHttpRequest; reply: (r: BridgeHttpReply) => void }[] = [];
  const shell = installOneWayShell((req, reply) => deferred.push({ req, reply: reply as (r: BridgeHttpReply) => void }));
  try {
    const client = bridgeHttpClient();
    const a = client.request("GET", "/v1/a");
    const b = client.request("GET", "/v1/b");
    await new Promise((r) => setTimeout(r, 10));
    assert.equal(deferred.length, 2, "both requests reached the shell");
    // Reply out of order, and give each a distinguishable status.
    const forA = deferred.find((d) => d.req.path === "/v1/a")!;
    const forB = deferred.find((d) => d.req.path === "/v1/b")!;
    forB.reply({ ok: true, response: { id: forB.req.id, status: 201, body: null } });
    forA.reply({ ok: true, response: { id: forA.req.id, status: 202, body: null } });
    assert.equal((await a).status, 202, "A got A's reply despite B answering first");
    assert.equal((await b).status, 201, "B got B's reply");
  } finally {
    shell.uninstall();
  }
});

test("an unknown or duplicate reply id is dropped, never applied to another request", async () => {
  let captured: ((r: BridgeHttpReply) => void) | null = null;
  let capturedId = "";
  const shell = installOneWayShell((req, reply) => {
    capturedId = req.id;
    captured = reply as (r: BridgeHttpReply) => void;
  });
  try {
    const client = bridgeHttpClient();
    const p = client.request("GET", "/v1/only");
    await new Promise((r) => setTimeout(r, 10));
    const g = globalThis as unknown as Record<string, unknown>;
    const sink = g[BRIDGE_HTTP_REPLY_FUNCTION] as (id: string, json: unknown) => void;
    // A reply for an id nobody is waiting on must not disturb the pending call.
    sink("h-nonexistent", JSON.stringify({ ok: true, response: { id: "h-nonexistent", status: 500, body: null } }));
    captured!({ ok: true, response: { id: capturedId, status: 200, body: null } });
    assert.equal((await p).status, 200, "the real reply won; the stray one was dropped");
    // A second (duplicate) reply for a settled id must be a no-op, not a throw.
    assert.doesNotThrow(() =>
      sink(capturedId, JSON.stringify({ ok: true, response: { id: capturedId, status: 500, body: null } })),
    );
  } finally {
    shell.uninstall();
  }
});

test("a lost reply becomes a retryable transport failure instead of stalling the outbox", async () => {
  const shell = installOneWayShell(() => {
    /* deliberately never replies */
  });
  try {
    const res = await bridgeHttpClient(40).request("GET", "/v1/action-items");
    assert.equal(res.status, BRIDGE_HTTP_FAILURE_STATUS["shell-error"]);
    assert.equal(res.json, null, "a lost reply has no HTTP body");
    assert.equal(classifyStatus(res, "lost reply").kind, "retryable", "the outbox must be able to retry, not hang");
  } finally {
    shell.uninstall();
  }
});

test("an unparseable one-way reply degrades to retryable", async () => {
  const shell = installOneWayShell((_req, reply) => reply("this is not json"));
  try {
    const res = await bridgeHttpClient(200).request("GET", "/v1/action-items");
    assert.equal(res.status, BRIDGE_HTTP_FAILURE_STATUS["shell-error"]);
    assert.equal(classifyStatus(res, "junk reply").kind, "retryable");
  } finally {
    shell.uninstall();
  }
});

// RED-PROOF (rule 14): remove the try/catch around JSON.stringify in
// bridge-http.ts and this circular body rejects the request instead of
// returning the documented retryable shell-error.
test("an unencodable request body degrades to retryable, never throws", async () => {
  const shell = installOneWayShell(() => {
    throw new Error("the channel must not see an unencodable body");
  });
  try {
    const circular: Record<string, unknown> = {};
    circular["self"] = circular;
    const res = await bridgeHttpClient(40).request("POST", "/v1/action-items", circular);
    assert.equal(res.status, BRIDGE_HTTP_FAILURE_STATUS["shell-error"]);
    assert.equal(classifyStatus(res, "unencodable body").kind, "retryable");
  } finally {
    shell.uninstall();
  }
});

/**
 * Precedence regression (wave-9, found on the simulator). webview_flutter
 * implements its one-way channel on iOS as a NON-reply webkit.messageHandlers
 * entry PLUS a window[CHANNEL] shim, so both look present. Preferring the
 * WebKit handler mis-detects Flutter as reply-capable: postMessage returns
 * undefined rather than a promise and every request silently degrades to a
 * transport failure, stalling the outbox while the shell serves nothing.
 *
 * RED-PROOF: reorder detectTransport to check webkit.messageHandlers first and
 * this test fails (it sees the reply-capable stub's 200 instead of the one-way
 * shim's 201).
 */
test("the one-way shim wins when a host exposes both, because Flutter exposes both", async () => {
  const g = globalThis as unknown as Record<string, unknown>;
  const prevWebkit = g["webkit"];
  const prevChannel = g[BRIDGE_HTTP_CHANNEL];
  // Emulate iOS exactly: a non-reply WebKit handler AND the forwarding shim.
  let shimUsed = false;
  g["webkit"] = {
    messageHandlers: {
      [BRIDGE_HTTP_CHANNEL]: {
        postMessage(): void {
          /* non-reply: returns undefined, exactly like Flutter's iOS handler */
        },
      },
    },
  };
  g[BRIDGE_HTTP_CHANNEL] = {
    postMessage(rawMsg: string): void {
      shimUsed = true;
      const req = JSON.parse(rawMsg) as BridgeHttpRequest;
      const sink = g[BRIDGE_HTTP_REPLY_FUNCTION] as (id: string, json: unknown) => void;
      sink(req.id, JSON.stringify({ ok: true, response: { id: req.id, status: 201, body: null } }));
    },
  };
  try {
    const res = await bridgeHttpClient(200).request("GET", "/v1/action-items");
    assert.equal(shimUsed, true, "the discriminating shim must be used, not the ambiguous WebKit handler");
    assert.equal(res.status, 201, "a 503 here means the non-reply handler was awaited and returned undefined");
  } finally {
    if (prevWebkit === undefined) delete g["webkit"];
    else g["webkit"] = prevWebkit;
    if (prevChannel === undefined) delete g[BRIDGE_HTTP_CHANNEL];
    else g[BRIDGE_HTTP_CHANNEL] = prevChannel;
  }
});

test("a reply-capable host with no shim is still detected as reply-capable (macOS shape)", async () => {
  const g = globalThis as unknown as Record<string, unknown>;
  delete g[BRIDGE_HTTP_CHANNEL]; // macOS installs no window[CHANNEL] global
  const shell = installShell((req) => ({ ok: true, response: { id: req.id, status: 200, body: null } }));
  try {
    const res = await bridgeHttpClient().request("GET", "/v1/action-items");
    assert.equal(res.status, 200, "macOS must keep using the promise-returning handler");
  } finally {
    shell.uninstall();
  }
});
