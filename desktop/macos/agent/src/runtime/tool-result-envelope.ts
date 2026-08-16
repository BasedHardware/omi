/**
 * Provider-safe result contract shared by every production adapter surface.
 * The envelope makes a bounded projection explicit and points at a canonical
 * local artifact whenever the complete result is larger than that projection.
 */
export const TOOL_RESULT_ENVELOPE_VERSION = 1 as const;

export interface ToolResultProvenance {
  invocationId: string;
  runId: string;
  attemptId: string;
  toolName: string;
}

export interface ToolResultEnvelope {
  version: typeof TOOL_RESULT_ENVELOPE_VERSION;
  status: "succeeded" | "failed" | "cancelled";
  truncated: boolean;
  originalBytes: number;
  projectedBytes: number;
  fullOutputRef: string | null;
  provenance: ToolResultProvenance;
}

export function makeToolResultEnvelope(input: Omit<ToolResultEnvelope, "version">): ToolResultEnvelope {
  const envelope: ToolResultEnvelope = { version: TOOL_RESULT_ENVELOPE_VERSION, ...input };
  assertToolResultEnvelope(envelope);
  return envelope;
}

/** Runtime guard for fixture, adapter, and transport boundaries. */
export function assertToolResultEnvelope(value: unknown): asserts value is ToolResultEnvelope {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Tool result envelope must be an object");
  }
  const envelope = value as Partial<ToolResultEnvelope>;
  if (envelope.version !== TOOL_RESULT_ENVELOPE_VERSION) {
    throw new Error("Unsupported tool result envelope version");
  }
  if (envelope.status !== "succeeded" && envelope.status !== "failed" && envelope.status !== "cancelled") {
    throw new Error("Tool result envelope status is invalid");
  }
  const originalBytes = envelope.originalBytes;
  const projectedBytes = envelope.projectedBytes;
  if (typeof envelope.truncated !== "boolean"
    || typeof originalBytes !== "number" || !Number.isSafeInteger(originalBytes) || originalBytes < 0
    || typeof projectedBytes !== "number" || !Number.isSafeInteger(projectedBytes) || projectedBytes < 0
    || (envelope.fullOutputRef !== null && typeof envelope.fullOutputRef !== "string")
    || !envelope.provenance
    || [envelope.provenance.invocationId, envelope.provenance.runId, envelope.provenance.attemptId, envelope.provenance.toolName]
      .some((value) => typeof value !== "string" || value.length === 0)) {
    throw new Error("Tool result envelope has an invalid field");
  }
  const checked = envelope as ToolResultEnvelope;
  if (checked.projectedBytes > checked.originalBytes) {
    throw new Error("Tool result envelope projected bytes exceed original bytes");
  }
  if (checked.truncated !== (checked.projectedBytes < checked.originalBytes)) {
    throw new Error("Tool result envelope truncation does not match byte projection");
  }
  if (checked.truncated && !checked.fullOutputRef) {
    throw new Error("Truncated tool result envelope requires a full output reference");
  }
}
