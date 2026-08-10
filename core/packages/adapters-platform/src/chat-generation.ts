/** Incremental observation of the ratified Chat generation SSE resource. */

import {
  CHAT_GENERATION_STREAM_CHANNEL,
  type BridgePayloadStream,
  type BridgeStreamPort,
  type ChatGenerationFrame,
  type ChatTerminalFrame,
} from "@omi-core/contracts";
import type { Env } from "@omi-core/kernel";
import { wireToChatGenerationFrame } from "./chat.js";

export interface ParsedChatGenerationEvent {
  readonly id: string;
  readonly frame: ChatGenerationFrame;
}

/**
 * Stateful UTF-8 + SSE parser. Bytes and every SSE field may be split across
 * arbitrary bridge chunks; multi-line data is joined with a newline exactly
 * once, per SSE.
 */
export class IncrementalChatGenerationParser {
  private readonly decoder = new TextDecoder("utf-8", { fatal: true });
  private text = "";
  private eventName: string | null = null;
  private eventId: string | null = null;
  private data: string[] = [];

  push(chunk: Uint8Array | string): readonly ParsedChatGenerationEvent[] {
    this.text += typeof chunk === "string"
      ? chunk
      : this.decoder.decode(chunk, { stream: true });
    return this.drainLines(false);
  }

  finish(): readonly ParsedChatGenerationEvent[] {
    this.text += this.decoder.decode();
    const events = [...this.drainLines(true)];
    if (this.eventName !== null || this.eventId !== null || this.data.length > 0) {
      throw new Error("truncated SSE event at stream end");
    }
    return events;
  }

  private drainLines(finishing: boolean): ParsedChatGenerationEvent[] {
    const events: ParsedChatGenerationEvent[] = [];
    while (this.text.length > 0) {
      let end = -1;
      let width = 0;
      for (let index = 0; index < this.text.length; index += 1) {
        const char = this.text[index];
        if (char === "\n") {
          end = index;
          width = 1;
          break;
        }
        if (char === "\r") {
          if (index === this.text.length - 1 && !finishing) return events;
          end = index;
          width = this.text[index + 1] === "\n" ? 2 : 1;
          break;
        }
      }
      if (end < 0) {
        if (!finishing) return events;
        const line = this.text;
        this.text = "";
        this.consumeLine(line, events);
        return events;
      }
      const line = this.text.slice(0, end);
      this.text = this.text.slice(end + width);
      this.consumeLine(line, events);
    }
    return events;
  }

  private consumeLine(line: string, events: ParsedChatGenerationEvent[]): void {
    if (line === "") {
      const event = this.dispatch();
      if (event !== null) events.push(event);
      return;
    }
    if (line.startsWith(":")) return;
    const colon = line.indexOf(":");
    const field = colon < 0 ? line : line.slice(0, colon);
    let value = colon < 0 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") this.eventName = value;
    else if (field === "id") {
      if (value.includes("\u0000")) throw new Error("SSE event id contains NUL");
      this.eventId = value;
    } else if (field === "data") {
      this.data.push(value);
    }
  }

  private dispatch(): ParsedChatGenerationEvent | null {
    if (this.data.length === 0) {
      this.resetEvent();
      return null;
    }
    const eventName = this.eventName;
    const eventId = this.eventId;
    const data = this.data.join("\n");
    this.resetEvent();
    if (eventName === null || eventName === "" || eventId === null || eventId === "") {
      throw new Error("generation SSE event requires opaque id and event name");
    }
    let raw: unknown;
    try {
      raw = JSON.parse(data) as unknown;
    } catch {
      throw new Error("generation SSE data is not JSON");
    }
    const frame = wireToChatGenerationFrame(raw);
    if (frame === null || frame.kind !== eventName) {
      throw new Error("generation SSE event name does not match its frame");
    }
    return { id: eventId, frame };
  }

  private resetEvent(): void {
    this.eventName = null;
    this.eventId = null;
    this.data = [];
  }
}

export type ChatGenerationObservationEvent =
  | { kind: "snapshot"; id: string; text: string }
  | { kind: "delta"; id: string; text: string }
  | { kind: "terminal"; id: string; terminal: ChatTerminalFrame }
  | { kind: "error"; failure: string };

export interface ChatGenerationObservation {
  readonly events: AsyncIterable<ChatGenerationObservationEvent>;
  cancel(reason?: string): void;
}

const INITIAL_GENERATION_CREDIT = 4;
const GENERATION_RECONNECT_DELAYS_MS = [250, 500, 1_000, 2_000, 4_000] as const;

function isTerminal(frame: ChatGenerationFrame): frame is ChatTerminalFrame {
  return frame.kind === "done" || frame.kind === "failed" || frame.kind === "cancelled";
}

/**
 * Open and reconnect one generation by exact opaque event id. Disconnect is
 * observation state only: it never calls POST and never acknowledges a write.
 */
export function observeChatGeneration(
  streamPort: BridgeStreamPort,
  generationId: string,
  env: Env,
  resumeAfterEventId?: string,
): ChatGenerationObservation {
  let cancelled = false;
  let active: BridgePayloadStream | null = null;
  let cancelReconnectDelay: (() => void) | null = null;
  const seenIds = new Set<string>(resumeAfterEventId === undefined ? [] : [resumeAfterEventId]);
  let lastEventId = resumeAfterEventId;

  const cancel = (reason?: string): void => {
    if (cancelled) return;
    cancelled = true;
    active?.cancel(reason ?? "generation-observation-cancelled");
    cancelReconnectDelay?.();
  };

  const waitToReconnect = async (delayMs: number): Promise<void> => {
    await new Promise<void>((resolve) => {
      let finished = false;
      let cancelTimer = (): void => undefined;
      const finish = (): void => {
        if (finished) return;
        finished = true;
        cancelTimer();
        cancelReconnectDelay = null;
        resolve();
      };
      cancelTimer = env.delay(delayMs, finish);
      cancelReconnectDelay = finish;
      if (cancelled) finish();
    });
  };

  const events = (async function* (): AsyncGenerator<ChatGenerationObservationEvent> {
    if (generationId === "") {
      yield { kind: "error", failure: "generation id is empty" };
      return;
    }
    let reconnectStep = 0;
    while (!cancelled) {
      const params = JSON.stringify({
        generationId,
        ...(lastEventId === undefined ? {} : { lastEventId }),
      });
      try {
        active = streamPort.open({
          channel: CHAT_GENERATION_STREAM_CHANNEL,
          params,
          initialCredit: INITIAL_GENERATION_CREDIT,
        });
      } catch (error) {
        yield { kind: "error", failure: String(error) };
        return;
      }
      const parser = new IncrementalChatGenerationParser();
      let firstFresh = true;
      let advancedCursor = false;
      try {
        for await (const chunk of active) {
          for (const event of parser.push(chunk)) {
            if (seenIds.has(event.id)) continue;
            seenIds.add(event.id);
            advancedCursor = true;
            if (firstFresh) {
              firstFresh = false;
              if (event.frame.kind !== "snapshot" && !isTerminal(event.frame)) {
                throw new Error("generation connection omitted its leading snapshot");
              }
            }
            lastEventId = event.id;
            if (event.frame.kind === "snapshot" || event.frame.kind === "delta") {
              yield { kind: event.frame.kind, id: event.id, text: event.frame.text };
              continue;
            }
            yield { kind: "terminal", id: event.id, terminal: event.frame };
            cancel("generation-terminal-observed");
            return;
          }
        }
        for (const event of parser.finish()) {
          if (seenIds.has(event.id)) continue;
          seenIds.add(event.id);
          advancedCursor = true;
          if (firstFresh && event.frame.kind !== "snapshot" && !isTerminal(event.frame)) {
            throw new Error("generation connection omitted its leading snapshot");
          }
          firstFresh = false;
          lastEventId = event.id;
          if (event.frame.kind === "snapshot" || event.frame.kind === "delta") {
            yield { kind: event.frame.kind, id: event.id, text: event.frame.text };
          } else {
            yield { kind: "terminal", id: event.id, terminal: event.frame };
            cancel("generation-terminal-observed");
            return;
          }
        }
      } catch (error) {
        active?.cancel("generation-observation-error");
        yield { kind: "error", failure: String(error) };
        return;
      } finally {
        active = null;
      }
      if (cancelled) return;
      if (lastEventId === undefined) {
        yield { kind: "error", failure: "generation disconnected before its first event" };
        return;
      }
      if (advancedCursor) reconnectStep = 0;
      if (reconnectStep >= GENERATION_RECONNECT_DELAYS_MS.length) {
        yield { kind: "error", failure: "generation observation reconnect limit reached" };
        return;
      }
      const delayMs = GENERATION_RECONNECT_DELAYS_MS[reconnectStep]!;
      reconnectStep += 1;
      await waitToReconnect(delayMs);
      // Reopen only after injected deterministic backoff, with the exact last
      // opaque event id. The host owns authentication and translates the value
      // to Last-Event-ID.
    }
  })();

  return { events, cancel };
}
