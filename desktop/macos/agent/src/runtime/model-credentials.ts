import type { ModelHeadersReply } from "./model-fetch.js";
import { randomUUID } from "node:crypto";
import type { Socket } from "node:net";

/** Ephemeral reply routing only; credential bytes are never retained or logged. */
export class ModelCredentialRelay {
  private pending = new Map<string, { client: Socket; callId: string; ownerId: string; capabilityRef: string; timer: ReturnType<typeof setTimeout> }>();
  constructor(
    private authorize: (capabilityRef: string, ownerId: string) => void,
    private send: (request: { type: "model_headers_request"; requestId: string; ownerId: string; forceRefresh: boolean }) => void,
  ) {}

  request(client: Socket, callId: string, capabilityRef: string, ownerId: string, forceRefresh: boolean): void {
    try { this.authorize(capabilityRef, ownerId); }
    catch { this.reply(client, callId, { failureCode: "authentication" }); return; }
    const requestId = randomUUID();
    const timer = setTimeout(() => {
      this.pending.delete(requestId);
      this.reply(client, callId, { failureCode: "transport_interruption" });
    }, 30_000);
    this.pending.set(requestId, { client, callId, ownerId, capabilityRef, timer });
    this.send({ type: "model_headers_request", requestId, ownerId, forceRefresh });
  }

  receive(requestId: string, payload: ModelHeadersReply, activeOwnerId: string): void {
    const pending = this.pending.get(requestId);
    if (!pending) return;
    clearTimeout(pending.timer);
    this.pending.delete(requestId);
    try {
      if (pending.ownerId !== activeOwnerId) throw new Error("owner changed");
      this.authorize(pending.capabilityRef, pending.ownerId);
      this.reply(pending.client, pending.callId, payload);
    } catch { this.reply(pending.client, pending.callId, { failureCode: "authentication" }); }
  }

  disconnect(client: Socket): void {
    for (const [id, pending] of this.pending) {
      if (pending.client !== client) continue;
      clearTimeout(pending.timer);
      this.pending.delete(id);
    }
  }

  private reply(client: Socket, callId: string, result: ModelHeadersReply): void {
    if (!client.destroyed) client.write(JSON.stringify({ type: "tool_result", callId, result: JSON.stringify(result) }) + "\n");
  }
}
