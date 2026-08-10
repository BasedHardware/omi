/** Web binding for the ratified credit-driven bridge stream lifecycle. */

import {
  BRIDGE_STREAM_MESSAGE_CHANNEL,
  BRIDGE_STREAM_SINK_FUNCTION,
  type BridgePayloadStream,
  type BridgeStreamOpenRequest,
  type BridgeStreamPort,
  type StreamFromShellWire,
  type StreamToShellWire,
} from "@omi-core/contracts";

interface MessageChannel {
  postMessage(message: string): unknown;
}

type IteratorResultValue = IteratorResult<string, undefined>;

export class BridgeStreamProtocolError extends Error {
  constructor(readonly violation: string) {
    super(`bridge stream protocol violation: ${violation}`);
    this.name = "BridgeStreamProtocolError";
  }
}

function detectChannel(): MessageChannel | null {
  const host = globalThis as unknown as {
    webkit?: { messageHandlers?: Record<string, MessageChannel | undefined> };
  } & Record<string, unknown>;
  const oneWay = host[BRIDGE_STREAM_MESSAGE_CHANNEL] as MessageChannel | undefined;
  if (oneWay && typeof oneWay.postMessage === "function") return oneWay;
  const replyCapable = host.webkit?.messageHandlers?.[BRIDGE_STREAM_MESSAGE_CHANNEL];
  return replyCapable && typeof replyCapable.postMessage === "function" ? replyCapable : null;
}

export function isBridgeStreamAvailable(): boolean {
  return detectChannel() !== null;
}

function isPositiveCredit(value: number): boolean {
  return Number.isSafeInteger(value) && value > 0;
}

function parseFrame(raw: unknown): StreamFromShellWire | null {
  if (typeof raw !== "string") return null;
  let value: unknown;
  try {
    value = JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const frame = value as Record<string, unknown>;
  if (typeof frame["id"] !== "string" || typeof frame["channel"] !== "string") return null;
  if (frame["t"] === "data" && typeof frame["payload"] === "string") {
    return { t: "data", id: frame["id"], channel: frame["channel"], payload: frame["payload"] };
  }
  if (frame["t"] === "end") {
    return { t: "end", id: frame["id"], channel: frame["channel"] };
  }
  if (frame["t"] === "error" && typeof frame["failure"] === "string") {
    return { t: "error", id: frame["id"], channel: frame["channel"], failure: frame["failure"] };
  }
  return null;
}

class Session implements BridgePayloadStream, AsyncIterator<string, undefined> {
  readonly id: string;
  readonly channel: string;
  private credit: number;
  private queue: string[] = [];
  private waiters: Array<{
    resolve: (result: IteratorResultValue) => void;
    reject: (error: Error) => void;
  }> = [];
  private terminal: { kind: "end" } | { kind: "error"; error: Error } | null = null;
  private settled = false;

  constructor(
    id: string,
    request: BridgeStreamOpenRequest,
    private readonly send: (message: StreamToShellWire) => void,
    private readonly retire: () => void,
  ) {
    this.id = id;
    this.channel = request.channel;
    this.credit = request.initialCredit;
  }

  [Symbol.asyncIterator](): AsyncIterator<string, undefined> {
    return this;
  }

  next(): Promise<IteratorResultValue> {
    if (this.queue.length > 0) {
      const value = this.queue.shift()!;
      this.grantOne();
      return Promise.resolve({ value, done: false });
    }
    if (this.terminal !== null) return this.terminalResult();
    return new Promise<IteratorResultValue>((resolve, reject) => {
      this.waiters.push({ resolve, reject });
    });
  }

  return(): Promise<IteratorResultValue> {
    this.cancel("consumer-return");
    return Promise.resolve({ value: undefined, done: true });
  }

  cancel(reason?: string): void {
    if (this.settled) return;
    this.settled = true;
    this.queue = [];
    this.terminal = { kind: "end" };
    this.retire();
    try {
      this.send({ t: "cancel", id: this.id, channel: this.channel, ...(reason ? { reason } : {}) });
    } catch {
      // Local cancellation is already terminal; a broken host cannot reopen it.
    } finally {
      this.flushTerminal();
    }
  }

  accept(frame: StreamFromShellWire): void {
    if (this.settled) return;
    if (frame.channel !== this.channel) {
      this.failProtocol("mismatched-channel");
      return;
    }
    if (frame.t === "data") {
      if (this.credit === 0) {
        this.failProtocol("credit-overrun");
        return;
      }
      this.credit -= 1;
      const waiter = this.waiters.shift();
      if (waiter) {
        waiter.resolve({ value: frame.payload, done: false });
        this.grantOne();
      } else {
        this.queue.push(frame.payload);
      }
      return;
    }
    this.settled = true;
    this.retire();
    this.terminal = frame.t === "end"
      ? { kind: "end" }
      : { kind: "error", error: new Error(`bridge stream shell error: ${frame.failure}`) };
    if (this.queue.length === 0) this.flushTerminal();
  }

  failMalformed(): void {
    this.failProtocol("malformed-frame");
  }

  private grantOne(): void {
    if (this.settled) return;
    this.credit += 1;
    try {
      this.send({ t: "grant", id: this.id, channel: this.channel, credit: 1 });
    } catch {
      this.failProtocol("grant-send-failed");
    }
  }

  private failProtocol(violation: string): void {
    if (this.settled) return;
    this.settled = true;
    this.queue = [];
    this.terminal = { kind: "error", error: new BridgeStreamProtocolError(violation) };
    this.retire();
    try {
      this.send({ t: "cancel", id: this.id, channel: this.channel, reason: violation });
    } catch {
      // The local protocol error remains the terminal outcome.
    }
    this.flushTerminal();
  }

  private terminalResult(): Promise<IteratorResultValue> {
    if (this.terminal?.kind === "error") return Promise.reject(this.terminal.error);
    return Promise.resolve({ value: undefined, done: true });
  }

  private flushTerminal(): void {
    if (this.terminal === null || this.queue.length > 0) return;
    const waiters = this.waiters.splice(0);
    if (this.terminal.kind === "error") {
      for (const waiter of waiters) waiter.reject(this.terminal.error);
    } else {
      for (const waiter of waiters) waiter.resolve({ value: undefined, done: true });
    }
  }
}

/** Bind streams to the native channel installed in the current document. */
export function bridgeStreamPort(): BridgeStreamPort {
  const host = detectChannel();
  if (!host) {
    throw new Error(`bridge stream unavailable: no "${BRIDGE_STREAM_MESSAGE_CHANNEL}" channel on this host`);
  }
  let sequence = 0;
  const sessions = new Map<string, Session>();
  const send = (message: StreamToShellWire): void => {
    host.postMessage(JSON.stringify(message));
  };

  (globalThis as unknown as Record<string, unknown>)[BRIDGE_STREAM_SINK_FUNCTION] = (raw: unknown): void => {
    const frame = parseFrame(raw);
    if (frame === null) {
      if (typeof raw !== "string") return;
      try {
        const partial = JSON.parse(raw) as { id?: unknown };
        if (typeof partial?.id === "string") sessions.get(partial.id)?.failMalformed();
      } catch {
        // Without a trustworthy id, malformed input cannot target any stream.
      }
      return;
    }
    sessions.get(frame.id)?.accept(frame);
  };

  return {
    open(request) {
      if (!isPositiveCredit(request.initialCredit)) {
        throw new BridgeStreamProtocolError("initial-credit-must-be-positive");
      }
      if (request.channel === "") throw new BridgeStreamProtocolError("channel-must-be-nonempty");
      sequence += 1;
      const id = `s${sequence}`;
      let session!: Session;
      session = new Session(id, request, send, () => sessions.delete(id));
      sessions.set(id, session);
      try {
        send({
          t: "open",
          id,
          channel: request.channel,
          params: request.params,
          credit: request.initialCredit,
        });
      } catch (error) {
        sessions.delete(id);
        throw error;
      }
      return session;
    },
  };
}
