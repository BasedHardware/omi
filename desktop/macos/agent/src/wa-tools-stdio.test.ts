import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import {
  requestScopeValue,
  stableJSONStringify,
  withIdempotencyKey,
} from "./wa-tools-stdio.js";

const baseContext = {
  requestId: "req-1",
  clientId: "client-1",
  sessionId: "ses-1",
  runId: "run-1",
  attemptId: "att-1",
};

const sendInput = {
  to: "1234567890@s.whatsapp.net",
  message: "hello",
};

function expectedClientMessageId(input: Record<string, unknown>): string {
  const to = typeof input.to === "string" ? input.to.trim() : "";
  const message = typeof input.message === "string" ? input.message : "";
  const logicalSend = {
    to,
    message,
    reply_to: typeof input.reply_to === "string" ? input.reply_to : undefined,
    reply_to_sender: typeof input.reply_to_sender === "string" ? input.reply_to_sender : undefined,
  };
  const hash = createHash("sha256")
    .update(stableJSONStringify(logicalSend))
    .digest("hex")
    .slice(0, 32);
  return `wa-tool:${hash}`;
}

describe("stableJSONStringify", () => {
  it("sorts object keys lexicographically", () => {
    const a = stableJSONStringify({ z: 1, a: 2, m: 3 });
    const b = stableJSONStringify({ m: 3, z: 1, a: 2 });
    expect(a).toBe('{"a":2,"m":3,"z":1}');
    expect(a).toBe(b);
  });

  it("recursively stabilizes nested objects and arrays", () => {
    expect(
      stableJSONStringify({
        outer: { b: 2, a: 1 },
        list: [{ y: 2, x: 1 }],
      }),
    ).toBe('{"list":[{"x":1,"y":2}],"outer":{"a":1,"b":2}}');
  });

  it("uses JSON.stringify for primitives", () => {
    expect(stableJSONStringify("hi")).toBe('"hi"');
    expect(stableJSONStringify(42)).toBe("42");
    expect(stableJSONStringify(null)).toBe("null");
    expect(stableJSONStringify(true)).toBe("true");
  });
});

describe("requestScopeValue", () => {
  it("returns trimmed non-empty strings", () => {
    expect(requestScopeValue("  rpc-42  ")).toBe("rpc-42");
  });

  it("returns undefined for blank strings", () => {
    expect(requestScopeValue("")).toBeUndefined();
    expect(requestScopeValue("   ")).toBeUndefined();
  });

  it("stringifies finite numbers", () => {
    expect(requestScopeValue(7)).toBe("7");
    expect(requestScopeValue(0)).toBe("0");
  });

  it("returns undefined for non-scalar values", () => {
    expect(requestScopeValue(null)).toBeUndefined();
    expect(requestScopeValue(undefined)).toBeUndefined();
    expect(requestScopeValue(NaN)).toBeUndefined();
    expect(requestScopeValue(Infinity)).toBeUndefined();
    expect(requestScopeValue({ id: 1 })).toBeUndefined();
  });
});

describe("withIdempotencyKey", () => {
  it("adds client_message_id for wa_send_message from logical send fields", () => {
    const result = withIdempotencyKey("wa_send_message", { ...sendInput }, baseContext, "rpc-1");
    expect(result.client_message_id).toBe(expectedClientMessageId(sendInput));
    expect(result).toEqual({ ...sendInput, client_message_id: result.client_message_id });
  });

  it("does not modify non-send tools", () => {
    const input = { query: "alice", limit: 10 };
    expect(withIdempotencyKey("wa_list_chats", input, baseContext, "rpc-1")).toBe(input);
    expect(withIdempotencyKey("wa_read_thread", { chat_jid: "x" }, baseContext, "rpc-1")).toEqual({
      chat_jid: "x",
    });
  });

  it("preserves existing client_message_id", () => {
    const input = { ...sendInput, client_message_id: "existing-id" };
    expect(withIdempotencyKey("wa_send_message", input, baseContext, "rpc-1")).toBe(input);
  });

  it("preserves existing dedupe_id", () => {
    const input = { ...sendInput, dedupe_id: "dedupe-1" };
    expect(withIdempotencyKey("wa_send_message", input, baseContext, "rpc-1")).toBe(input);
  });

  it("still generates a key when request scope is missing", () => {
    const input = { ...sendInput };
    const result = withIdempotencyKey("wa_send_message", input, baseContext, null);
    expect(result.client_message_id).toBe(expectedClientMessageId(sendInput));
  });

  it("returns input unchanged when to/message are missing", () => {
    expect(withIdempotencyKey("wa_send_message", { to: "x" }, baseContext, "rpc-1")).toEqual({ to: "x" });
    expect(withIdempotencyKey("wa_send_message", { message: "hi" }, baseContext, "rpc-1")).toEqual({
      message: "hi",
    });
  });

  it("produces deterministic hashes for the same logical send", () => {
    const first = withIdempotencyKey("wa_send_message", { ...sendInput }, baseContext, 99);
    const second = withIdempotencyKey("wa_send_message", { ...sendInput }, baseContext, 99);
    expect(first.client_message_id).toBe(second.client_message_id);
    expect(first.client_message_id).toMatch(/^wa-tool:[0-9a-f]{32}$/);
  });

  it("keeps the same key across different request scopes (retry-safe)", () => {
    const first = withIdempotencyKey("wa_send_message", { ...sendInput }, baseContext, "rpc-1");
    const retried = withIdempotencyKey(
      "wa_send_message",
      { ...sendInput },
      { ...baseContext, requestId: "req-2", runId: "run-2", attemptId: "att-2" },
      "rpc-2",
    );
    expect(retried.client_message_id).toBe(first.client_message_id);
  });

  it("changes the hash when the logical send differs", () => {
    const base = withIdempotencyKey("wa_send_message", { ...sendInput }, baseContext, "rpc-1");
    const otherMessage = withIdempotencyKey(
      "wa_send_message",
      { ...sendInput, message: "goodbye" },
      baseContext,
      "rpc-1",
    );
    const otherRecipient = withIdempotencyKey(
      "wa_send_message",
      { ...sendInput, to: "999@s.whatsapp.net" },
      baseContext,
      "rpc-1",
    );
    const withReply = withIdempotencyKey(
      "wa_send_message",
      { ...sendInput, reply_to: "msg-1" },
      baseContext,
      "rpc-1",
    );

    expect(otherMessage.client_message_id).not.toBe(base.client_message_id);
    expect(otherRecipient.client_message_id).not.toBe(base.client_message_id);
    expect(withReply.client_message_id).not.toBe(base.client_message_id);
  });
});
