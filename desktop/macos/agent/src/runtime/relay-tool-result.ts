import { createHash, randomUUID } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import type { AgentRuntimeKernel } from "./kernel.js";
import { assertToolResultEnvelope, makeToolResultEnvelope, type ToolResultEnvelope } from "./tool-result-envelope.js";

/** One budget applies to every result put back on a model-facing stdio relay. */
export const MAX_RELAY_TOOL_RESULT_BYTES = 8 * 1024;

/**
 * Marker key carried by every budget-truncated relay payload. It sits beside
 * the partial content so a model that reads only the payload still learns that
 * the result is incomplete and how to reach the rest.
 */
export const RELAY_TRUNCATION_KEY = "outputTruncated";

/** In-line marker appended to a head-sliced string so the cut is self-evident. */
export const RELAY_TRUNCATION_SUFFIX = "\n…[output truncated]";

/**
 * The single recovery sentence for both the truncated projection and the
 * terminal budget failure. Naming the recovery tools is what makes the
 * reference actionable — `fullOutputRef` alone is not a call the model can make.
 */
const RELAY_FULL_OUTPUT_RECOVERY =
  "The complete output was saved locally; use its fullOutputRef with `read_tool_output` or `search_tool_output` to read the rest.";

export interface RelayToolResultIdentity {
  invocationId: string;
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  toolName: string;
}

export interface FinalizeRelayToolResultInput {
  identity: RelayToolResultIdentity;
  result: string;
  outcome?: "succeeded" | "failed" | "cancelled";
  kernel?: AgentRuntimeKernel;
  artifactRoot: string;
}

/**
 * The final model-facing result boundary for the normal stdio relay.
 *
 * Swift-backed execution, timeout, authority rejection, and control-tool
 * output all pass here before the adapter receives a `tool_result` frame. A
 * source envelope is validated but never trusted for provenance: the pending
 * capability is the authoritative invocation identity. Outputs that cannot fit
 * are persisted and then degraded — a marked head projection beside the
 * canonical artifact reference — and become a typed recoverable failure only
 * when no usable head fits the budget.
 */
export function finalizeRelayToolResult(input: FinalizeRelayToolResultInput): string {
  const rawBytes = Buffer.byteLength(input.result, "utf8");
  const parsed = parseObject(input.result);
  const sourceEnvelope = parsed ? validEnvelope(parsed.toolResultEnvelope) : undefined;
  const payload = parsed
    ? withoutEnvelope(parsed)
    : input.outcome === "succeeded"
      // Swift-backed tools may return a legitimate human-readable success
      // rather than a JSON object. Preserve it as an explicit bounded text
      // projection instead of manufacturing a malformed-result failure.
      ? { text: input.result }
      : {
        error: {
          code: "malformed_tool_result",
          message: "The tool executor returned malformed output.",
        },
      };
  // A Swift transport receipt may be marked succeeded even when the tool's
  // structured payload reports a legitimate tool failure. The model-visible
  // envelope is canonical: it must agree with both the outer `ok` and the
  // kernel invocation outcome derived after this finalizer.
  const payloadFailed = payload.ok === false || Object.hasOwn(payload, "error");
  const status = input.outcome === "failed" || sourceEnvelope?.status === "failed" || payloadFailed
    ? "failed"
    : sourceEnvelope?.status === "cancelled" ? "cancelled" : "succeeded";
  const payloadBytes = Buffer.byteLength(JSON.stringify(payload), "utf8");
  // A pre-enveloped source measures its payload, not the JSON bytes occupied
  // by its previous envelope. Rewrapping it must not turn every normal result
  // into a needless artifact-backed truncation.
  const originalBytes = sourceEnvelope
    ? Math.max(sourceEnvelope.originalBytes, payloadBytes)
    : Math.max(rawBytes, payloadBytes);
  let fullOutputRef = sourceEnvelope?.fullOutputRef ?? null;
  const sourceWasTruncated = sourceEnvelope?.truncated === true;
  const needsArtifact = sourceWasTruncated || (!sourceEnvelope && originalBytes > payloadBytes);

  if (needsArtifact && !fullOutputRef) {
    fullOutputRef = persistRelayToolOutput(input, input.result);
  }
  if (needsArtifact && !fullOutputRef) {
    return projectionFailure(input, originalBytes, null, "tool_result_artifact_unavailable");
  }

  // A hostile or stale producer can claim that its source envelope is already
  // truncated while putting the complete payload back beside that envelope.
  // Do not construct an impossible `truncated: true` envelope whose projected
  // bytes are as large as (or larger than) its original bytes; deliver a
  // genuinely smaller head projection so the claim becomes true, and fall back
  // to the bounded artifact-backed failure only when nothing fits.
  if (needsArtifact && payloadBytes >= originalBytes) {
    const truncated = fullOutputRef
      ? truncatedRelayProjection({ input, payload, status, originalBytes: payloadBytes, fullOutputRef })
      : null;
    if (truncated) return truncated;
    return projectionFailure(
      input,
      payloadBytes,
      fullOutputRef,
      "tool_result_projection_exceeded_budget",
    );
  }

  const envelope = makeToolResultEnvelope({
    status,
    truncated: needsArtifact,
    originalBytes,
    projectedBytes: payloadBytes,
    fullOutputRef,
    provenance: provenance(input.identity),
  });
  const candidate = JSON.stringify({
    ...payload,
    ok: status === "succeeded",
    toolResultEnvelope: envelope,
  });
  if (Buffer.byteLength(candidate, "utf8") <= MAX_RELAY_TOOL_RESULT_BYTES) {
    return candidate;
  }

  // The complete projection does not fit. Persist it, then hand back the
  // largest head slice that does fit instead of discarding the result: a
  // marked partial answer plus a durable reference is strictly more useful to
  // the model than an empty budget failure, which loses a successful tool call
  // entirely.
  const recoveredRef = fullOutputRef ?? persistRelayToolOutput(input, input.result);
  if (recoveredRef) {
    const truncated = truncatedRelayProjection({
      input,
      payload,
      status,
      originalBytes,
      fullOutputRef: recoveredRef,
    });
    if (truncated) return truncated;
  }
  return projectionFailure(input, originalBytes, recoveredRef, "tool_result_projection_exceeded_budget");
}

interface RelayTruncationInput {
  input: FinalizeRelayToolResultInput;
  payload: Record<string, unknown>;
  status: ToolResultEnvelope["status"];
  originalBytes: number;
  fullOutputRef: string;
}

/**
 * The payload field a budget-truncated projection shrinks. Arrays lose whole
 * trailing elements so the remaining structure stays parseable; strings lose a
 * byte-bounded tail. Everything else in the payload is preserved verbatim.
 */
interface RelayShrinkTarget {
  /** Key path from the payload root. Rendered dotted as the marker's `field`. */
  path: string[];
  kind: "items" | "text";
  /** Element count for `items`, UTF-8 byte length for `text`. */
  total: number;
  project: (keep: number) => unknown;
}

/** Bounds the shrink-target search over an arbitrarily nested tool payload. */
const MAX_RELAY_SHRINK_DEPTH = 6;

/**
 * Build the largest head projection of `payload` whose finalized relay frame
 * still fits the budget, or `null` when not even a one-unit head fits.
 *
 * The frame is measured, never estimated: JSON escaping, the marker, and the
 * envelope all vary in size, so each candidate is serialized and checked. The
 * search is monotone in `keep`, so a binary search finds the largest fit.
 */
function truncatedRelayProjection(truncation: RelayTruncationInput): string | null {
  const target = shrinkTarget(truncation.payload);
  if (!target) return null;

  const build = (keep: number): string | null => {
    const notice: Record<string, unknown> = {
      reason: "relay_result_exceeded_budget",
      field: target.path.join("."),
      fullOutputRef: truncation.fullOutputRef,
      message: RELAY_FULL_OUTPUT_RECOVERY,
    };
    if (target.kind === "items") {
      notice.shownItems = keep;
      notice.totalItems = target.total;
    }
    const projected: Record<string, unknown> = {
      ...replaceAtPath(truncation.payload, target.path, target.project(keep)),
      [RELAY_TRUNCATION_KEY]: notice,
    };
    const projectedBytes = Buffer.byteLength(JSON.stringify(projected), "utf8");
    // A projection that is not smaller than the original cannot be described by
    // a `truncated: true` envelope, so it is not a candidate.
    if (projectedBytes >= truncation.originalBytes) return null;
    const frame = JSON.stringify({
      ...projected,
      ok: truncation.status === "succeeded",
      toolResultEnvelope: makeToolResultEnvelope({
        status: truncation.status,
        truncated: true,
        originalBytes: truncation.originalBytes,
        projectedBytes,
        fullOutputRef: truncation.fullOutputRef,
        provenance: provenance(truncation.input.identity),
      }),
    });
    return Buffer.byteLength(frame, "utf8") <= MAX_RELAY_TOOL_RESULT_BYTES ? frame : null;
  };

  // `low` starts at 1: an empty head is the total loss this projection exists
  // to avoid, so it is never an acceptable answer.
  let low = 1;
  let high = target.total;
  let fitted: string | null = null;
  while (low <= high) {
    const midpoint = Math.floor((low + high) / 2);
    const frame = build(midpoint);
    if (frame) {
      fitted = frame;
      low = midpoint + 1;
    } else {
      high = midpoint - 1;
    }
  }
  return fitted;
}

/**
 * Pick the largest shrinkable field anywhere in the payload; the rest of the
 * payload is rebuilt whole around it. Nested plain objects are searched too,
 * because a wrapper such as `{ ok: true, data: { items: [...] } }` otherwise
 * has no shrinkable field at the top level and would be discarded entirely.
 */
function shrinkTarget(payload: Record<string, unknown>): RelayShrinkTarget | null {
  const best: { path: string[]; value: unknown; bytes: number } = { path: [], value: null, bytes: 0 };

  const visit = (value: unknown, path: string[]): void => {
    if (path.length > MAX_RELAY_SHRINK_DEPTH) return;
    const bytes = Buffer.byteLength(JSON.stringify(value) ?? "", "utf8");
    const shrinkable = (Array.isArray(value) && value.length > 0)
      || (typeof value === "string" && value.length > 0);
    if (shrinkable && bytes > best.bytes) {
      best.path = path;
      best.value = value;
      best.bytes = bytes;
    }
    if (Array.isArray(value) || !value || typeof value !== "object") return;
    for (const [key, child] of Object.entries(value as Record<string, unknown>)) {
      if (path.length === 0 && key === RELAY_TRUNCATION_KEY) continue;
      visit(child, [...path, key]);
    }
  };
  visit(payload, []);

  if (best.path.length === 0) return null;
  if (Array.isArray(best.value)) {
    const items = best.value;
    return { path: best.path, kind: "items", total: items.length, project: (keep) => items.slice(0, keep) };
  }
  const text = best.value as string;
  return {
    path: best.path,
    kind: "text",
    total: Buffer.byteLength(text, "utf8"),
    project: (keep) => `${truncateUtf8Head(text, keep)}${RELAY_TRUNCATION_SUFFIX}`,
  };
}

/** Rebuild `root` with `value` substituted at `path`, copying only that spine. */
function replaceAtPath(root: Record<string, unknown>, path: string[], value: unknown): Record<string, unknown> {
  const [head, ...rest] = path;
  if (head === undefined) return root;
  if (rest.length === 0) return { ...root, [head]: value };
  const child = root[head];
  return {
    ...root,
    [head]: replaceAtPath((child ?? {}) as Record<string, unknown>, rest, value),
  };
}

/**
 * Head-slice `text` to at most `maxBytes` UTF-8 bytes without splitting a code
 * point. Cutting by JS string index can split a surrogate pair and emit a lone
 * surrogate, so the cut is made on the encoded buffer and walked back off any
 * continuation byte to the preceding lead byte.
 */
function truncateUtf8Head(text: string, maxBytes: number): string {
  const buffer = Buffer.from(text, "utf8");
  if (buffer.byteLength <= maxBytes) return text;
  let end = Math.max(maxBytes, 0);
  while (end > 0 && (buffer[end] & 0xc0) === 0x80) end -= 1;
  return buffer.subarray(0, end).toString("utf8");
}

/**
 * The kernel ledger derives its terminal outcome from this finalized boundary,
 * never from an untrusted pre-finalization receipt. Both normal and external
 * pending Swift completion paths call this exact helper.
 */
export function finalizedToolResultOutcome(result: string): "succeeded" | "failed" {
  const payload = parseObject(result);
  const envelope = payload ? validEnvelope(payload.toolResultEnvelope) : undefined;
  if (envelope) return envelope.status === "succeeded" ? "succeeded" : "failed";
  return payload?.ok === true ? "succeeded" : "failed";
}

function parseObject(value: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : null;
  } catch {
    return null;
  }
}

function withoutEnvelope(value: Record<string, unknown>): Record<string, unknown> {
  const { toolResultEnvelope: _toolResultEnvelope, ...payload } = value;
  return payload;
}

function validEnvelope(value: unknown): ToolResultEnvelope | undefined {
  try {
    assertToolResultEnvelope(value);
    return value;
  } catch {
    return undefined;
  }
}

function provenance(identity: RelayToolResultIdentity): ToolResultEnvelope["provenance"] {
  return {
    invocationId: identity.invocationId,
    runId: identity.runId,
    attemptId: identity.attemptId,
    toolName: identity.toolName,
  };
}

function projectionFailure(
  input: FinalizeRelayToolResultInput,
  originalBytes: number,
  fullOutputRef: string | null,
  code: "tool_result_artifact_unavailable" | "tool_result_projection_exceeded_budget",
): string {
  const payload = {
    error: {
      code,
      message: code === "tool_result_projection_exceeded_budget"
        ? `Tool output exceeded the relay result budget. ${RELAY_FULL_OUTPUT_RECOVERY}`
        : "Tool output could not be retained safely, so it was not delivered.",
    },
  };
  const payloadBytes = Buffer.byteLength(JSON.stringify(payload), "utf8");
  const recoverable = fullOutputRef !== null && originalBytes > payloadBytes;
  return JSON.stringify({
    ok: false,
    ...payload,
    toolResultEnvelope: makeToolResultEnvelope({
      status: "failed",
      truncated: recoverable,
      originalBytes: recoverable ? originalBytes : payloadBytes,
      projectedBytes: payloadBytes,
      fullOutputRef: recoverable ? fullOutputRef : null,
      provenance: provenance(input.identity),
    }),
  });
}

function persistRelayToolOutput(input: FinalizeRelayToolResultInput, fullResult: string): string | null {
  if (!input.kernel) return null;
  try {
    const directory = join(input.artifactRoot, "tool-output", input.identity.ownerId, input.identity.sessionId);
    mkdirSync(directory, { recursive: true });
    const path = join(directory, `relay-${randomUUID()}.json`);
    writeFileSync(path, `${fullResult}\n`, "utf8");
    const artifact = input.kernel.persistArtifact({
      sessionId: input.identity.sessionId,
      kind: "tool_output",
      role: "tool_output",
      uri: pathToFileURL(path).toString(),
      displayName: `${input.identity.toolName} relay output`,
      mimeType: "application/json",
      contentHash: `sha256:${createHash("sha256").update(fullResult).digest("hex")}`,
      sizeBytes: Buffer.byteLength(fullResult, "utf8"),
      metadata: {
        toolName: input.identity.toolName,
        projection: "relay_bounded",
        ownerId: input.identity.ownerId,
        invocationId: input.identity.invocationId,
      },
    });
    return `artifact:${artifact.artifactId}`;
  } catch {
    return null;
  }
}
