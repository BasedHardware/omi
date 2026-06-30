import { createHash } from "node:crypto";
import type {
  DesktopContextPolicyDecision,
  DesktopContextRetentionClass,
  DesktopContextSourceKind,
  NewDesktopContextAccessLog,
} from "./types.js";

export interface DesktopContextSnippetInput {
  snippetId: string;
  sourceKind: DesktopContextSourceKind;
  operation: string;
  provenance: Record<string, unknown>;
  content?: string;
  redactedContent?: string;
  metadata?: Record<string, unknown>;
  sensitivityTier: string;
  policyDecision?: DesktopContextPolicyDecision;
  selected?: boolean;
  tokenEstimate?: number;
}

export interface DesktopContextPacketBuildInput {
  ownerId: string;
  sessionId?: string | null;
  runId?: string | null;
  surfaceKind: string;
  objective: string;
  snippets: readonly DesktopContextSnippetInput[];
  selectedToolBundles?: readonly string[];
  constraints?: readonly string[];
  evidenceRequired?: readonly string[];
  boundaryPolicy?: Record<string, unknown>;
  retentionClass: DesktopContextRetentionClass;
  ttlMs?: number;
  nowMs?: number;
  packetId?: string;
}

export interface BuiltDesktopContextPacket {
  packet: {
    packetId: string;
    ownerId: string;
    sessionId: string | null;
    runId: string | null;
    surfaceKind: string;
    objective: string;
    packetJson: Record<string, unknown>;
    redactedPreviewJson: Record<string, unknown>;
    contextHash: string;
    tokenEstimate: number;
    retentionClass: DesktopContextRetentionClass;
    expiresAtMs: number;
    createdAtMs: number;
  };
  accessLogs: NewDesktopContextAccessLog[];
}

function stableJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, entry]) => `${JSON.stringify(key)}:${stableJson(entry)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function estimateTokens(value: string): number {
  return Math.max(1, Math.ceil(value.length / 4));
}

function assertNoScreenshotBytes(snippet: DesktopContextSnippetInput): void {
  const candidates = [snippet.content, snippet.redactedContent, ...(Object.values(snippet.metadata ?? {}) as unknown[])];
  for (const candidate of candidates) {
    if (typeof candidate !== "string") continue;
    if (/^data:image\//i.test(candidate) || /^[A-Za-z0-9+/]{400,}={0,2}$/.test(candidate)) {
      throw new Error(`Context snippet ${snippet.snippetId} appears to contain raw screenshot image bytes.`);
    }
  }
}

function packetIdFor(input: DesktopContextPacketBuildInput, createdAtMs: number): string {
  if (input.packetId) return input.packetId;
  const hash = createHash("sha256")
    .update(`${input.ownerId}:${input.surfaceKind}:${input.objective}:${createdAtMs}`)
    .digest("hex")
    .slice(0, 16);
  return `ctx_${hash}`;
}

export function buildDesktopContextPacket(input: DesktopContextPacketBuildInput): BuiltDesktopContextPacket {
  if (!Number.isFinite(input.ttlMs) || (input.ttlMs ?? 0) <= 0) {
    throw new Error("DesktopContextPacket requires a positive TTL.");
  }
  const nowMs = input.nowMs ?? Date.now();
  const selected = input.snippets.filter((snippet) => snippet.selected !== false);
  for (const snippet of selected) assertNoScreenshotBytes(snippet);

  const snippets = selected.map((snippet) => ({
    snippetId: snippet.snippetId,
    sourceKind: snippet.sourceKind,
    operation: snippet.operation,
    provenance: snippet.provenance,
    content: snippet.content ?? "",
    metadata: snippet.metadata ?? {},
    sensitivityTier: snippet.sensitivityTier,
    tokenEstimate: snippet.tokenEstimate ?? estimateTokens(snippet.content ?? ""),
  }));
  const redactedSnippets = selected.map((snippet) => ({
    snippetId: snippet.snippetId,
    sourceKind: snippet.sourceKind,
    operation: snippet.operation,
    provenance: snippet.provenance,
    preview: snippet.redactedContent ?? "[redacted]",
    sensitivityTier: snippet.sensitivityTier,
  }));
  const packetJson = {
    objective: input.objective,
    surfaceKind: input.surfaceKind,
    snippets,
    selectedToolBundles: [...(input.selectedToolBundles ?? [])],
    constraints: [...(input.constraints ?? [])],
    evidenceRequired: [...(input.evidenceRequired ?? [])],
    boundaryPolicy: input.boundaryPolicy ?? {},
  };
  const redactedPreviewJson = {
    objective: input.objective,
    surfaceKind: input.surfaceKind,
    snippets: redactedSnippets,
    selectedToolBundles: [...(input.selectedToolBundles ?? [])],
  };
  const contextHash = `sha256:${createHash("sha256").update(stableJson(packetJson)).digest("hex")}`;
  const tokenEstimate = snippets.reduce((sum, snippet) => sum + snippet.tokenEstimate, estimateTokens(input.objective));
  const packetId = packetIdFor(input, nowMs);
  const accessLogs: NewDesktopContextAccessLog[] = selected.map((snippet) => ({
    ownerId: input.ownerId,
    packetId,
    runId: input.runId ?? null,
    sourceKind: snippet.sourceKind,
    operation: snippet.operation,
    scopeJson: JSON.stringify(snippet.provenance),
    sensitivityTier: snippet.sensitivityTier,
    policyDecision: snippet.policyDecision ?? "allowed",
    redactionSummaryJson: JSON.stringify({
      previewOnly: true,
      contentIncluded: snippet.content !== undefined,
      redactedPreview: snippet.redactedContent !== undefined,
    }),
  }));

  return {
    packet: {
      packetId,
      ownerId: input.ownerId,
      sessionId: input.sessionId ?? null,
      runId: input.runId ?? null,
      surfaceKind: input.surfaceKind,
      objective: input.objective,
      packetJson,
      redactedPreviewJson,
      contextHash,
      tokenEstimate,
      retentionClass: input.retentionClass,
      expiresAtMs: nowMs + input.ttlMs!,
      createdAtMs: nowMs,
    },
    accessLogs,
  };
}

export const desktopContextPacketInternals = {
  stableJson,
};
