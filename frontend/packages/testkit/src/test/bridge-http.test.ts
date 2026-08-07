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
  type BridgeHttpFailureReason,
  type BridgeHttpReply,
  type BridgeHttpRequest,
} from "@omi-core/contracts";
import { bridgeHttpClient, isBridgeHttpAvailable } from "@omi-core/bridge-web";
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
