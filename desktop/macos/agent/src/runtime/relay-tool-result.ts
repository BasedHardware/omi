import { createHash, randomUUID } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import type { AgentRuntimeKernel } from "./kernel.js";
import { assertToolResultEnvelope, makeToolResultEnvelope, type ToolResultEnvelope } from "./tool-result-envelope.js";

/** One budget applies to every result put back on a model-facing stdio relay. */
export const MAX_RELAY_TOOL_RESULT_BYTES = 8 * 1024;

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
 * capability is the authoritative invocation identity. Outputs that cannot
 * fit are persisted before a typed recoverable failure is returned.
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
  // bytes are as large as (or larger than) its original bytes; return the
  // bounded artifact-backed projection instead.
  if (needsArtifact && payloadBytes >= originalBytes) {
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

  const recoveredRef = fullOutputRef ?? persistRelayToolOutput(input, input.result);
  return projectionFailure(input, originalBytes, recoveredRef, "tool_result_projection_exceeded_budget");
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
        ? "Tool output was saved locally; use fullOutputRef to inspect the complete result."
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
