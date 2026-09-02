import { createHash, randomUUID } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import type { AgentRuntimeKernel } from "./kernel.js";
import { maybePruneExpiredToolOutputs, TOOL_OUTPUT_DIRECTORY_NAME } from "./artifact-storage.js";
import { assertToolResultEnvelope, makeToolResultEnvelope, type ToolResultEnvelope } from "./tool-result-envelope.js";
import {
  DEFAULT_MODEL_TOOL_RESULT_BUDGET_BYTES,
  projectionIsComplete,
  projectToolResultPayload,
  toolResultBudgetBytes,
  utf8Excerpt,
} from "./tool-result-projector.js";

/** One budget applies to every result put back on a model-facing stdio relay. */
export const MAX_RELAY_TOOL_RESULT_BYTES = DEFAULT_MODEL_TOOL_RESULT_BUDGET_BYTES;

export interface RelayToolResultIdentity {
  invocationId: string;
  ownerId: string;
  sessionId: string;
  runId: string;
  attemptId: string;
  toolName: string;
  surfaceKind?: string;
  purpose?: string;
}

export interface FinalizeRelayToolResultInput {
  identity: RelayToolResultIdentity;
  result: string;
  outcome?: "succeeded" | "failed" | "cancelled";
  kernel?: AgentRuntimeKernel;
  artifactRoot: string;
  onDegraded?: (record: { toolName: string; originalBytes: number; projectedBytes: number }) => void;
}

/**
 * The final model-facing result boundary for the normal stdio relay.
 *
 * Swift-backed execution, timeout, authority rejection, and control-tool
 * output all pass here before the adapter receives a `tool_result` frame. A
 * source envelope is validated but never trusted for provenance: the pending
 * capability is the authoritative invocation identity. Outputs that cannot
 * fit are persisted before a typed successful projection is returned.
 */
export function finalizeRelayToolResult(input: FinalizeRelayToolResultInput): string {
  const purpose = input.identity.purpose ? utf8Excerpt(input.identity.purpose, 256) : undefined;
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
  const executorBytes = sourceEnvelope
    ? Math.max(sourceEnvelope.originalBytes, payloadBytes)
    : Math.max(rawBytes, payloadBytes);
  const originalBytes = sourceEnvelope ? executorBytes : payloadBytes;
  let fullOutputRef = sourceEnvelope?.fullOutputRef ?? null;
  const sourceWasTruncated = sourceEnvelope?.truncated === true;
  const needsArtifact = sourceWasTruncated;

  if (needsArtifact && !fullOutputRef) {
    fullOutputRef = persistRelayToolOutput(input, input.result);
  }
  // Persistence is an observability/recovery concern, never execution
  // authority. A storage outage cannot rewrite executor success as failure.

  const budget = toolResultBudgetBytes(
    input.identity.toolName,
    input.identity.surfaceKind === "realtime" || input.identity.surfaceKind === "realtime_voice"
      ? "realtime_voice"
      : "desktop_chat",
  );
  // Rewrapping can make an upstream truncated payload as large as (or larger
  // than) its recorded original size. Do not construct an invalid envelope:
  // only the consistent pair reaches makeToolResultEnvelope; otherwise the
  // normal projection path below establishes a fresh bounded measurement.
  if (!needsArtifact || payloadBytes < originalBytes) {
    // An untruncated source envelope can carry a stale/larger byte count from
    // a serialization layer we remove here. Completeness is authoritative, so
    // normalize the pair to this payload instead of constructing an envelope
    // whose byte delta falsely implies truncation.
    const passthroughOriginalBytes = needsArtifact ? originalBytes : payloadBytes;
    const envelope = makeToolResultEnvelope({
      status,
      truncated: needsArtifact,
      originalBytes: passthroughOriginalBytes,
      projectedBytes: payloadBytes,
      fullOutputRef,
      provenance: provenance(input.identity),
    });
    const candidate = JSON.stringify({
      ...payload,
      ok: status === "succeeded",
      toolResultEnvelope: envelope,
    });
    if (Buffer.byteLength(candidate, "utf8") <= budget) return candidate;
  }

  for (let reserve = 768; reserve < budget; reserve += 256) {
    const projection = projectToolResultPayload({
      toolName: input.identity.toolName,
      result: input.result,
      purpose,
      maxBytes: Math.max(0, budget - reserve),
    });
    const projectedBytes = Buffer.byteLength(JSON.stringify(projection), "utf8");
    const truncated = !projectionIsComplete(projection);
    if (truncated && projectedBytes >= executorBytes) continue;
    const projectedOriginalBytes = truncated ? executorBytes : projectedBytes;
    const projectedRef = truncated
      ? fullOutputRef ?? persistRelayToolOutput(input, input.result) ?? "artifact:unavailable"
      : null;
    const projected = JSON.stringify({
      ok: status === "succeeded",
      ...projection,
      toolResultEnvelope: makeToolResultEnvelope({
        status,
        truncated,
        originalBytes: projectedOriginalBytes,
        projectedBytes,
        fullOutputRef: projectedRef,
        purpose,
        provenance: provenance(input.identity),
      }),
    });
    if (Buffer.byteLength(projected, "utf8") <= budget) {
      if (truncated) {
        input.onDegraded?.({ toolName: input.identity.toolName, originalBytes: projectedOriginalBytes, projectedBytes });
      }
      return projected;
    }
  }
  const recoveredRef = fullOutputRef ?? persistRelayToolOutput(input, input.result) ?? "artifact:unavailable";
  const minimalProjection = { text: "Tool result available via fullOutputRef.", omitted: {} };
  const minimalBytes = Buffer.byteLength(JSON.stringify(minimalProjection), "utf8");
  const minimal = JSON.stringify({
    ok: status === "succeeded",
    ...minimalProjection,
    toolResultEnvelope: makeToolResultEnvelope({
      status,
      truncated: true,
      originalBytes: executorBytes,
      projectedBytes: minimalBytes,
      fullOutputRef: recoveredRef,
      provenance: provenance(input.identity),
    }),
  });
  input.onDegraded?.({ toolName: input.identity.toolName, originalBytes: executorBytes, projectedBytes: minimalBytes });
  return minimal;
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

function persistRelayToolOutput(input: FinalizeRelayToolResultInput, fullResult: string): string | null {
  if (!input.kernel) return null;
  try {
    const directory = join(input.artifactRoot, TOOL_OUTPUT_DIRECTORY_NAME, input.identity.ownerId, input.identity.sessionId);
    mkdirSync(directory, { recursive: true });
    const path = join(directory, `relay-${randomUUID()}.json`);
    writeFileSync(path, `${fullResult}\n`, "utf8");
    maybePruneExpiredToolOutputs(input.artifactRoot);
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
