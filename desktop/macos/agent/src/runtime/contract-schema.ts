/** Minimal deterministic JSON-Schema validator for the versioned shared
 * runtime fixture. Keeping this dependency-free makes the Node harness and the
 * Swift fixture test validate the same checked-in schema in hermetic CI. */
export interface RuntimeContractSchema {
  type?: string | string[];
  const?: unknown;
  enum?: unknown[];
  minLength?: number;
  minimum?: number;
  minItems?: number;
  required?: string[];
  properties?: Record<string, RuntimeContractSchema>;
  items?: RuntimeContractSchema;
  additionalProperties?: boolean;
}

export function validateRuntimeContractSchema(
  value: unknown,
  schema: RuntimeContractSchema,
  path = "$",
): string[] {
  const errors: string[] = [];
  const types = schema.type === undefined ? [] : Array.isArray(schema.type) ? schema.type : [schema.type];
  if (types.length > 0 && !types.some((type) => matchesType(value, type))) {
    return [`${path}: expected ${types.join(" | ")}`];
  }
  if (schema.const !== undefined && value !== schema.const) errors.push(`${path}: const mismatch`);
  if (schema.enum && !schema.enum.includes(value)) errors.push(`${path}: value is outside enum`);
  if (typeof value === "string" && schema.minLength !== undefined && value.length < schema.minLength) {
    errors.push(`${path}: string is shorter than minLength`);
  }
  if (typeof value === "number" && schema.minimum !== undefined && value < schema.minimum) {
    errors.push(`${path}: number is below minimum`);
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) errors.push(`${path}: array has too few items`);
    if (schema.items) value.forEach((item, index) => errors.push(...validateRuntimeContractSchema(item, schema.items!, `${path}[${index}]`)));
  }
  if (isRecord(value)) {
    for (const key of schema.required ?? []) {
      if (!(key in value)) errors.push(`${path}: missing ${key}`);
    }
    const properties = schema.properties ?? {};
    if (schema.additionalProperties === false) {
      for (const key of Object.keys(value)) {
        if (!(key in properties)) errors.push(`${path}: unexpected ${key}`);
      }
    }
    for (const [key, childSchema] of Object.entries(properties)) {
      if (key in value) errors.push(...validateRuntimeContractSchema(value[key], childSchema, `${path}.${key}`));
    }
  }
  return errors;
}

/**
 * JSON Schema deliberately covers the portable shape; these identity and
 * transition checks cover relationships JSON Schema cannot express without a
 * non-hermetic extension. Keep them beside the schema validator so every Node
 * contract consumer executes the same fixture boundary.
 */
export function validateRuntimeContractFixture(
  value: unknown,
  schema: RuntimeContractSchema,
): string[] {
  const errors = validateRuntimeContractSchema(value, schema);
  if (!isRecord(value)) return errors;
  const envelope = isRecord(value.toolResultEnvelope) ? value.toolResultEnvelope : undefined;
  const provenance = envelope && isRecord(envelope.provenance) ? envelope.provenance : undefined;
  const invocation = isRecord(value.toolInvocation) ? value.toolInvocation : undefined;
  const permission = isRecord(value.permissionDecision) ? value.permissionDecision : undefined;
  if (provenance && invocation) {
    for (const field of ["invocationId", "runId", "attemptId", "toolName"] as const) {
      if (provenance[field] !== invocation[field]) errors.push(`$.toolInvocation.${field}: does not match envelope provenance`);
    }
  }
  if (provenance && permission && permission.invocationId !== provenance.invocationId) {
    errors.push("$.permissionDecision.invocationId: does not match envelope provenance");
  }
  if (envelope) {
    const truncated = envelope.truncated;
    const originalBytes = envelope.originalBytes;
    const projectedBytes = envelope.projectedBytes;
    if (typeof originalBytes === "number" && typeof projectedBytes === "number") {
      if (projectedBytes > originalBytes) errors.push("$.toolResultEnvelope: projected bytes exceed original bytes");
      if ((projectedBytes < originalBytes) !== truncated) errors.push("$.toolResultEnvelope: truncation does not match byte projection");
    }
    if (truncated === true && typeof envelope.fullOutputRef !== "string") {
      errors.push("$.toolResultEnvelope.fullOutputRef: truncated output requires an artifact reference");
    }
  }
  const lifecycle = isRecord(value.lifecycle) ? value.lifecycle : undefined;
  const expectedLifecycle: Record<string, string[]> = {
    session: ["open", "archived", "closed"],
    run: [
      "queued", "starting", "running", "waiting_input", "waiting_approval", "cancelling", "succeeded", "failed",
      "cancelled", "timed_out", "orphaned",
    ],
    attempt: [
      "queued", "starting", "running", "waiting_input", "waiting_approval", "cancelling", "succeeded", "failed",
      "cancelled", "timed_out", "orphaned",
    ],
    turn: ["pending", "streaming", "completed", "failed"],
  };
  if (lifecycle) {
    for (const [name, expected] of Object.entries(expectedLifecycle)) {
      if (!Array.isArray(lifecycle[name]) || lifecycle[name].join("|") !== expected.join("|")) {
        errors.push(`$.lifecycle.${name}: must declare the complete production state set`);
      }
    }
  }
  const taxonomy = Array.isArray(value.failureTaxonomy) ? value.failureTaxonomy : [];
  const expectedTaxonomy = [
    "authentication", "quota_exceeded", "invalid_request", "timeout", "transport_interruption", "adapter_unavailable",
    "adapter_incompatible", "bridge_start_failed", "provider_setup_needed", "malformed_or_oversized_tool_result",
    "cancelled", "stale_owner", "policy_denied", "unknown",
  ];
  if (taxonomy.join("|") !== expectedTaxonomy.join("|")) {
    errors.push("$.failureTaxonomy: must declare the complete bounded production taxonomy");
  }
  const adapters = Array.isArray(value.adapterConformance) ? value.adapterConformance : [];
  const expectedAdapters = ["pi-mono", "acp", "hermes", "openclaw", "codex", "gemini-realtime", "openai-realtime"];
  if (adapters.map((adapter) => isRecord(adapter) ? adapter.adapterId : undefined).join("|") !== expectedAdapters.join("|")) {
    errors.push("$.adapterConformance: must cover every production adapter exactly once");
  }
  for (const [index, adapter] of adapters.entries()) {
    if (!isRecord(adapter) || !Array.isArray(adapter.scenarios)) continue;
    const names = adapter.scenarios.map((scenario) => isRecord(scenario) ? scenario.name : undefined);
    if (names.join("|") !== "lifecycle_failure|oversized_tool_result") {
      errors.push(`$.adapterConformance[${index}].scenarios: must execute lifecycle and oversized-result cases`);
    }
  }
  return errors;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function matchesType(value: unknown, type: string): boolean {
  switch (type) {
    case "object": return isRecord(value);
    case "array": return Array.isArray(value);
    case "string": return typeof value === "string";
    case "boolean": return typeof value === "boolean";
    case "number": return typeof value === "number" && Number.isFinite(value);
    case "integer": return typeof value === "number" && Number.isInteger(value);
    case "null": return value === null;
    default: return false;
  }
}
