/** Domain contracts — mirror backend/models/memories.py core fields. */

export type MemoryCategory =
  | "interesting"
  | "system"
  | "manual"
  | "workflow"
  | "core"
  | "hobbies"
  | "lifestyle"
  | "interests"
  | "habits"
  | "work"
  | "skills"
  | "learnings"
  | "other"
  | "auto";

export type MemoryLayer = "short_term" | "long_term" | "archive";

export type SubjectAttribution = "user" | "third_party" | "unknown" | "legacy_assumed";

export type MemoryEvidence = {
  artifact_ref: Record<string, unknown>;
  capture_confidence: number;
  client_device_id: string | null;
  created_at: string;
  evidence_id: string;
  extractor_id: string;
  extractor_version: string;
  independence_group: string;
  redaction_status: string;
  source_id: string | null;
  source_signal: string;
  source_type: string;
};

export type MemoryRecord = {
  id: string;
  uid: string;
  content: string;
  category: MemoryCategory;
  app_id: string | null;
  arguments: Record<string, unknown>;
  capture_confidence: number | null;
  capture_device_ids: string[];
  conversation_id: string | null;
  created_at: string;
  data_protection_level: string | null;
  durability: string | null;
  edited: boolean;
  evidence: MemoryEvidence[];
  headline: string | null;
  invalid_at: string | null;
  is_baseline: boolean;
  is_locked: boolean;
  kg_extracted: boolean;
  layer: MemoryLayer | null;
  manually_added: boolean;
  memory_id: string | null;
  memory_tier: MemoryLayer | null;
  object_entity_ids: string[];
  predicate: string | null;
  primary_capture_device: string | null;
  qualifiers: Record<string, unknown>;
  reviewed: boolean;
  subject_attribution: SubjectAttribution;
  subject_entity_id: string | null;
  superseded_by: string | null;
  tags: string[];
  uncertainty_reasons: string[];
  updated_at: string;
  user_review: boolean | null;
  valid_at: string | null;
  veracity: number | null;
  visibility: string | null;
};

export type ListMemoriesInput = {
  uid: string;
  limit?: number;
  offset?: number;
  cursor?: string;
  deviceScope?: string;
  clientDeviceId?: string;
};

export type MemoryStore = {
  list(input: ListMemoriesInput): Promise<MemoryRecord[]>;
  get(uid: string, id: string): Promise<MemoryRecord | null>;
};

/** Origin (Python API) adapter — no local DB yet. */
export function originMemoryStore(originBase: string, authHeader: string): MemoryStore {
  const base = originBase.replace(/\/$/, "");
  return {
    async list(input) {
      const qs = new URLSearchParams();
      if (input.limit !== undefined) qs.set("limit", String(input.limit));
      if (input.offset !== undefined) qs.set("offset", String(input.offset));
      if (input.cursor !== undefined) qs.set("cursor", input.cursor);
      if (input.deviceScope !== undefined) qs.set("device_scope", input.deviceScope);
      if (input.clientDeviceId !== undefined) qs.set("client_device_id", input.clientDeviceId);
      const res = await fetch(`${base}/v3/memories?${qs}`, {
        headers: { Authorization: authHeader, "x-omi-edge": "memory-origin" },
      });
      if (!res.ok) throw new Error(`origin_memories_${res.status}`);
      const body = (await res.json()) as unknown;
      return normalizeMemoryList(body, input.uid);
    },
    async get(uid, id) {
      const res = await fetch(`${base}/v3/memories/${id}`, {
        headers: { Authorization: authHeader, "x-omi-edge": "memory-origin" },
      });
      if (res.status === 404) return null;
      if (!res.ok) throw new Error(`origin_memory_${res.status}`);
      const body = (await res.json()) as Record<string, unknown>;
      return normalizeMemory(body, uid);
    },
  };
}

function normalizeMemoryList(body: unknown, uid: string): MemoryRecord[] {
  const arr = Array.isArray(body)
    ? body
    : body && typeof body === "object" && Array.isArray((body as { memories?: unknown }).memories)
      ? (body as { memories: unknown[] }).memories
      : [];
  return arr
    .map((row) => normalizeMemory(row as Record<string, unknown>, uid))
    .filter((m): m is MemoryRecord => m !== null);
}

function normalizeMemory(row: Record<string, unknown>, uid: string): MemoryRecord | null {
  if (!row || typeof row !== "object") return null;
  const id = String(row.id ?? row.memory_id ?? "");
  const createdAt = stringValue(row.created_at);
  const updatedAt = stringValue(row.updated_at);
  if (!id || !createdAt || !updatedAt) return null;
  return {
    id,
    uid: String(row.uid ?? uid),
    content: String(row.content ?? ""),
    category: (String(row.category ?? "interesting") as MemoryCategory) || "interesting",
    app_id: nullableString(row.app_id),
    arguments: objectValue(row.arguments),
    capture_confidence: numberValue(row.capture_confidence),
    capture_device_ids: stringArray(row.capture_device_ids),
    conversation_id: nullableString(row.conversation_id),
    created_at: createdAt,
    data_protection_level: nullableString(row.data_protection_level),
    durability: nullableString(row.durability),
    edited: booleanValue(row.edited, false),
    evidence: evidenceArray(row.evidence),
    headline: nullableString(row.headline),
    invalid_at: nullableString(row.invalid_at),
    is_baseline: booleanValue(row.is_baseline, false),
    is_locked: booleanValue(row.is_locked, false),
    kg_extracted: booleanValue(row.kg_extracted, false),
    layer: layerValue(row.layer),
    manually_added: booleanValue(row.manually_added, false),
    memory_id: nullableString(row.memory_id) ?? id,
    memory_tier: layerValue(row.memory_tier),
    object_entity_ids: stringArray(row.object_entity_ids),
    predicate: nullableString(row.predicate),
    primary_capture_device: nullableString(row.primary_capture_device),
    qualifiers: objectValue(row.qualifiers),
    reviewed: booleanValue(row.reviewed, false),
    subject_attribution: subjectAttributionValue(row.subject_attribution),
    subject_entity_id: nullableString(row.subject_entity_id),
    superseded_by: nullableString(row.superseded_by),
    tags: stringArray(row.tags),
    uncertainty_reasons: stringArray(row.uncertainty_reasons),
    updated_at: updatedAt,
    user_review: nullableBoolean(row.user_review),
    valid_at: nullableString(row.valid_at),
    veracity: numberValue(row.veracity),
    visibility: nullableString(row.visibility) ?? "public",
  };
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

function nullableBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function booleanValue(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function layerValue(value: unknown): MemoryLayer | null {
  return value === "short_term" || value === "long_term" || value === "archive" ? value : null;
}

function subjectAttributionValue(value: unknown): SubjectAttribution {
  return value === "user" || value === "third_party" || value === "legacy_assumed" ? value : "unknown";
}

function evidenceArray(value: unknown): MemoryEvidence[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object"))
    .map((item) => ({
      artifact_ref: objectValue(item.artifact_ref),
      capture_confidence: numberValue(item.capture_confidence) ?? 0.5,
      client_device_id: nullableString(item.client_device_id),
      created_at: nullableString(item.created_at) ?? "",
      evidence_id: String(item.evidence_id ?? ""),
      extractor_id: String(item.extractor_id ?? "unknown"),
      extractor_version: String(item.extractor_version ?? "unknown"),
      independence_group: String(item.independence_group ?? ""),
      redaction_status: String(item.redaction_status ?? "active"),
      source_id: nullableString(item.source_id),
      source_signal: String(item.source_signal ?? "unknown"),
      source_type: String(item.source_type ?? "unknown"),
    }));
}
