import { describe, expect, it, vi } from "vitest";
import type { Socket } from "node:net";
import { ModelCredentialRelay } from "../src/runtime/model-credentials.js";

function fixture() {
  const client = { destroyed: false, write: vi.fn() } as unknown as Socket;
  const authorize = vi.fn();
  const send = vi.fn();
  return { client, authorize, send, relay: new ModelCredentialRelay(authorize, send) };
}

describe("request-scoped credential relay", () => {
  it("revalidates the run and owner after Swift's asynchronous reply", () => {
    const { client, authorize, send, relay } = fixture();
    relay.request(client, "call", "cap", "owner", false);
    const id = send.mock.calls[0][0].requestId;
    authorize.mockImplementation(() => { throw new Error("revoked"); });
    relay.receive(id, { headers: { Authorization: "Bearer inert-test-only" } }, "owner");
    expect(JSON.parse(String(vi.mocked(client.write).mock.calls[0][0])).result).toBe(JSON.stringify({ failureCode: "authentication" }));
    expect(authorize).toHaveBeenCalledTimes(2);
  });
  it("routes one response then forgets it; disconnected clients receive nothing", () => {
    const { client, send, relay } = fixture();
    relay.request(client, "call", "cap", "owner", true);
    const request = send.mock.calls[0][0];
    expect(request).toMatchObject({ type: "model_headers_request", forceRefresh: true, ownerId: "owner" });
    relay.receive(request.requestId, { headers: { Authorization: "Bearer inert-test-only" } }, "owner");
    relay.receive(request.requestId, {}, "owner");
    expect(client.write).toHaveBeenCalledTimes(1);
    relay.request(client, "other", "cap", "owner", false);
    relay.disconnect(client);
    relay.receive(send.mock.calls[1][0].requestId, {}, "owner");
    expect(client.write).toHaveBeenCalledTimes(1);
  });
});
