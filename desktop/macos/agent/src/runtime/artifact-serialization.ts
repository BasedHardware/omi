import type { SerializedArtifact } from "../protocol.js";
import type { AgentArtifact } from "./types.js";

export function serializeArtifact(artifact: AgentArtifact): SerializedArtifact {
  return {
    artifactId: artifact.artifactId,
    omiSessionId: artifact.sessionId,
    runId: artifact.runId,
    attemptId: artifact.attemptId,
    kind: artifact.kind,
    role: artifact.role,
    uri: artifact.uri,
    displayName: artifact.displayName,
    mimeType: artifact.mimeType,
    contentHash: artifact.contentHash,
    sizeBytes: artifact.sizeBytes,
    lifecycleState: artifact.lifecycleState,
    lifecycleUpdatedAtMs: artifact.lifecycleUpdatedAtMs,
    metadata: parseJsonObject(artifact.metadataJson),
    createdAtMs: artifact.createdAtMs,
  };
}

export function parseJsonObject(value: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}
