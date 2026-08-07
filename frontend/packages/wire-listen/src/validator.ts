/**
 * Minimal JSON Schema (draft 2020-12) validator — the subset the /listen schema
 * actually uses. Ported from prototypes/listen-schema/conformance/validator.mjs.
 */

const UUID_RE = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

type JsonSchema = Record<string, unknown> & {
  $ref?: string;
  type?: string | string[];
  const?: unknown;
  enum?: unknown[];
  required?: string[];
  properties?: Record<string, JsonSchema>;
  items?: JsonSchema;
  additionalProperties?: boolean;
  minimum?: number;
  format?: string;
  "x-omi-opaque"?: boolean;
  "x-omi-open-enum"?: boolean;
  "x-omi-role"?: string;
  "x-omi-event-type"?: string;
  "x-omi-message-type"?: string;
};

export interface SchemaDocument {
  $defs: Record<string, JsonSchema>;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function matchesType(type: string, value: unknown): boolean {
  switch (type) {
    case "null":
      return value === null;
    case "string":
      return typeof value === "string";
    case "boolean":
      return typeof value === "boolean";
    case "integer":
      return typeof value === "number" && Number.isInteger(value);
    case "number":
      return typeof value === "number";
    case "array":
      return Array.isArray(value);
    case "object":
      return isPlainObject(value);
    default:
      throw new Error(`unknown type keyword ${type}`);
  }
}

function describe(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
}

export class Validator {
  constructor(private readonly document: SchemaDocument) {}

  deref(schema: JsonSchema): JsonSchema {
    let current: JsonSchema = schema;
    let guard = 0;
    while (current.$ref) {
      if (guard++ > 32) throw new Error("$ref cycle");
      const m = /^#\/\$defs\/(.+)$/.exec(current.$ref);
      if (!m) throw new Error(`unsupported $ref ${current.$ref}`);
      const next = this.document.$defs[m[1]!];
      if (!next) throw new Error(`missing $def ${m[1]}`);
      current = next;
    }
    return current;
  }

  /** Returns an array of error strings; empty means valid. */
  validate(schema: JsonSchema, value: unknown, path = "$"): string[] {
    const s = this.deref(schema);
    const errors: string[] = [];
    if (s["x-omi-opaque"]) return errors;

    if (s.const !== undefined && value !== s.const) {
      errors.push(`${path}: expected const ${JSON.stringify(s.const)}, got ${JSON.stringify(value)}`);
      return errors;
    }

    const types = s.type === undefined ? null : Array.isArray(s.type) ? s.type : [s.type];
    if (types && !types.some((t) => matchesType(t, value))) {
      errors.push(`${path}: expected type ${types.join("|")}, got ${describe(value)}`);
      return errors;
    }

    if (value === null) return errors;

    if (Array.isArray(s.enum) && !s.enum.includes(value)) {
      if (!s["x-omi-open-enum"]) {
        errors.push(`${path}: ${JSON.stringify(value)} not in enum ${JSON.stringify(s.enum)}`);
      }
    }

    if (typeof value === "number" && s.minimum !== undefined && value < s.minimum) {
      errors.push(`${path}: ${value} < minimum ${s.minimum}`);
    }
    if (typeof value === "string" && s.format === "uuid" && !UUID_RE.test(value)) {
      errors.push(`${path}: ${JSON.stringify(value)} is not a uuid`);
    }

    if (Array.isArray(value)) {
      if (s.items) {
        value.forEach((item, i) => errors.push(...this.validate(s.items!, item, `${path}[${i}]`)));
      }
      return errors;
    }

    if (isPlainObject(value)) {
      for (const key of s.required ?? []) {
        if (!(key in value)) errors.push(`${path}: missing required property ${JSON.stringify(key)}`);
      }
      const props = s.properties ?? {};
      for (const [key, child] of Object.entries(value)) {
        if (props[key]) {
          errors.push(...this.validate(props[key]!, child, `${path}.${key}`));
        } else if (s.additionalProperties === false) {
          errors.push(`${path}: unexpected property ${JSON.stringify(key)}`);
        }
      }
    }
    return errors;
  }
}

/** Index server-event / client-message defs by their wire `type` string. */
export function indexByWireType(
  document: SchemaDocument,
  roleKey: string,
  typeKey: "x-omi-event-type" | "x-omi-message-type",
): Map<string, { name: string; def: JsonSchema }> {
  const out = new Map<string, { name: string; def: JsonSchema }>();
  for (const [name, def] of Object.entries(document.$defs)) {
    if (def["x-omi-role"] === roleKey) {
      const wireType = def[typeKey];
      if (typeof wireType === "string") out.set(wireType, { name, def });
    }
  }
  return out;
}
