import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import {
  BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL,
  BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION,
  type BridgeChatAttachmentStagingRequest,
} from "@omi-core/contracts";
import {
  bridgeChatAttachmentStagingPort,
  isBridgeChatAttachmentStagingAvailable,
} from "@omi-core/bridge-web";

const host = globalThis as unknown as Record<string, unknown>;

afterEach(() => {
  Reflect.deleteProperty(host, BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL);
  Reflect.deleteProperty(host, BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION);
});

test("absent native staging is explicitly unsupported and never fabricates an id", async () => {
  assert.equal(isBridgeChatAttachmentStagingAvailable(), false);
  const port = bridgeChatAttachmentStagingPort();
  assert.equal(port.isAvailable(), false);
  await assert.rejects(port.pickAndStage(), /attachment staging unavailable/);
});

test("one-way host receives only pick intent and returns a sanitized safe descriptor", async () => {
  // red-proof: put caller metadata or a file payload on the request. The exact
  // request shape assertion below exposes the forbidden field at the host wire.
  const requests: BridgeChatAttachmentStagingRequest[] = [];
  host[BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL] = {
    postMessage(raw: string): void {
      const request = JSON.parse(raw) as BridgeChatAttachmentStagingRequest;
      requests.push(request);
      const reply = host[BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION] as
        (id: string, rawReply: string) => void;
      reply(request.id, JSON.stringify({
        ok: true,
        id: request.id,
        attachment: {
          id: "opaque-stage-1",
          displayName: "server-normalized.pdf",
          mimeType: "application/pdf",
          sizeBytes: 1234,
          expiresAt: "2026-08-11T12:00:00.000Z",
          state: "staged",
          localPath: "/private/user-secret.pdf",
          token: "must-not-escape",
        },
      }));
    },
  };

  const port = bridgeChatAttachmentStagingPort();
  assert.equal(port.isAvailable(), true);
  assert.deepEqual(await port.pickAndStage(), {
    id: "opaque-stage-1",
    displayName: "server-normalized.pdf",
    mimeType: "application/pdf",
    sizeBytes: 1234,
    expiresAt: "2026-08-11T12:00:00.000Z",
    state: "staged",
  });
  assert.deepEqual(requests, [{ t: "pick-and-stage", id: requests[0]!.id }]);
  assert.deepEqual(Object.keys(requests[0]!).sort(), ["id", "t"]);
});

test("cancel and unsafe native metadata never create a staged descriptor", async () => {
  let reply: unknown = { ok: false, id: "a1", reason: "cancelled" };
  host[BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL] = {
    postMessage(raw: string): void {
      const request = JSON.parse(raw) as BridgeChatAttachmentStagingRequest;
      const settle = host[BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION] as
        (id: string, rawReply: string) => void;
      settle(request.id, JSON.stringify({ ...(reply as object), id: request.id }));
    },
  };
  const cancelled = bridgeChatAttachmentStagingPort();
  assert.equal(await cancelled.pickAndStage(), null);

  reply = {
    ok: true,
    id: "unused",
    attachment: {
      id: "https://forbidden.example/id",
      displayName: "../caller-name.pdf",
      mimeType: "caller/type",
      sizeBytes: 10,
      expiresAt: "not-an-expiry",
      state: "staged",
    },
  };
  await assert.rejects(cancelled.pickAndStage(), /unsafe descriptor/);
});

test("two staging ports share collision-proof realm reply routing", async () => {
  const requests: BridgeChatAttachmentStagingRequest[] = [];
  host[BRIDGE_CHAT_ATTACHMENT_STAGING_CHANNEL] = {
    postMessage(raw: string): void {
      requests.push(JSON.parse(raw) as BridgeChatAttachmentStagingRequest);
    },
  };
  const firstPort = bridgeChatAttachmentStagingPort();
  const secondPort = bridgeChatAttachmentStagingPort();
  const first = firstPort.pickAndStage();
  const second = secondPort.pickAndStage();

  assert.equal(requests.length, 2);
  assert.notEqual(requests[0]!.id, requests[1]!.id, "realm staging ids must never reset per port");
  const reply = host[BRIDGE_CHAT_ATTACHMENT_STAGING_REPLY_FUNCTION] as
    (id: string, rawReply: string) => void;
  for (const [index, request] of requests.entries()) {
    reply(request.id, JSON.stringify({
      ok: true,
      id: request.id,
      attachment: {
        id: `opaque-stage-${index + 1}`,
        displayName: `server-${index + 1}.pdf`,
        mimeType: "application/pdf",
        sizeBytes: index + 1,
        expiresAt: "2026-08-11T12:00:00.000Z",
        state: "staged",
      },
    }));
  }
  assert.equal((await first)?.id, "opaque-stage-1");
  assert.equal((await second)?.id, "opaque-stage-2");
});
