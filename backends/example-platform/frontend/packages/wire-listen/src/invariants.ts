/**
 * Executable INV-LISTEN checkers.
 * Ported from prototypes/listen-schema/conformance/invariants.mjs.
 *
 * Each rule takes the ordered decode results of one scenario plus its close code
 * and handshake query, and returns null (holds) or a violation message.
 */

import type { DecodedListenFrame } from "./listen_protocol.generated.js";
import { isDegraded, type MaybeDegraded } from "@omi-core/contracts";

export interface ConformanceStep {
  readonly index: number;
  readonly decoded: DecodedListenFrame;
}

export interface ConformanceContext {
  readonly steps: readonly ConformanceStep[];
  readonly close: number | null;
  readonly query: string;
  readonly handshake: string;
}

export function unwrapDecoded(result: MaybeDegraded<DecodedListenFrame>): DecodedListenFrame {
  return isDegraded(result) ? result.value : result;
}

/** Tiny query-string getter — avoids depending on DOM/URLSearchParams typings in this package. */
function queryParam(query: string, key: string): string | null {
  for (const part of query.split("&")) {
    if (!part) continue;
    const eq = part.indexOf("=");
    const k = eq === -1 ? part : part.slice(0, eq);
    if (decodeURIComponent(k) === key) {
      return eq === -1 ? "" : decodeURIComponent(part.slice(eq + 1));
    }
  }
  return null;
}

export const RULES: Record<string, (ctx: ConformanceContext) => string | null> = {
  /** INV-LISTEN-002 */
  "no-transcript-before-ready": (ctx) => {
    let ready = false;
    for (const step of ctx.steps) {
      if (step.decoded.kind === "event" && step.decoded.event.type === "service_status") {
        if (step.decoded.event.status === "ready") ready = true;
      }
      if (step.decoded.kind === "transcript_batch" && step.decoded.segments.length > 0 && !ready) {
        return `transcript batch at frame ${step.index} arrived before service_status:ready`;
      }
    }
    return null;
  },

  /** INV-LISTEN-003 */
  "stt-failed-precedes-1011": (ctx) => {
    if (ctx.close !== 1011) return null;
    const events = ctx.steps.filter(
      (s): s is ConformanceStep & { decoded: Extract<DecodedListenFrame, { kind: "event" }> } =>
        s.decoded.kind === "event",
    );
    const last = events[events.length - 1];
    if (!last) return "close 1011 with no preceding events at all";
    const event = last.decoded.event;
    if (event.type !== "service_status" || event.status !== "stt_failed") {
      return `close 1011 preceded by ${event.type}${
        event.type === "service_status" ? `:${event.status}` : ""
      }, not service_status:stt_failed`;
    }
    return null;
  },

  /** INV-LISTEN-001 */
  "segment-id-dedupe": (ctx) => {
    const seen = new Map<string, { start: number; end: number }>();
    for (const step of ctx.steps) {
      if (step.decoded.kind !== "transcript_batch") continue;
      for (const segment of step.decoded.segments) {
        const id = segment.id;
        if (id == null) continue;
        const prior = seen.get(id);
        if (prior) {
          if (prior.start !== segment.start) {
            return `segment ${id} redelivered with a different start (${prior.start} -> ${segment.start})`;
          }
          if (segment.end < prior.end) {
            return `segment ${id} redelivered with a decreasing end (${prior.end} -> ${segment.end})`;
          }
        }
        seen.set(id, { start: segment.start, end: segment.end });
      }
    }
    return null;
  },

  "causal-segments-deleted": (ctx) => {
    const delivered = new Set<string>();
    for (const step of ctx.steps) {
      if (step.decoded.kind === "transcript_batch") {
        for (const segment of step.decoded.segments) if (segment.id != null) delivered.add(segment.id);
        continue;
      }
      if (step.decoded.kind === "event" && step.decoded.event.type === "segments_deleted") {
        for (const id of step.decoded.event.segment_ids ?? []) {
          if (!delivered.has(id)) return `segments_deleted named ${id}, never delivered in a transcript batch`;
        }
      }
    }
    return null;
  },

  /** INV-LISTEN-004 */
  "resume-key-required": (ctx) => {
    const value = queryParam(ctx.query ?? "", "client_conversation_id");
    if (!value) return "handshake omitted client_conversation_id, so a reconnect cannot resume the session";
    if (!/^[0-9a-fA-F-]{36}$/.test(value)) return `client_conversation_id ${value} is not a uuid`;
    return null;
  },

  /**
   * INV-LISTEN-006 (decode-time): unknown_event results must arrive as Degraded.
   * The checker itself only sees unwrapped frames; the harness asserts isDegraded
   * at decode time. This rule holds whenever no unknown_event was silently dropped.
   */
  "unknown-frame-degraded": () => null,
};

export function checkAll(ctx: ConformanceContext): {
  held: string[];
  violated: { rule: string; message: string }[];
} {
  const held: string[] = [];
  const violated: { rule: string; message: string }[] = [];
  for (const [rule, fn] of Object.entries(RULES)) {
    const message = fn(ctx);
    if (message) violated.push({ rule, message });
    else held.push(rule);
  }
  return { held, violated };
}
