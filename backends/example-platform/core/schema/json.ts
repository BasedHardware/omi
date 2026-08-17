import Ajv2020 from "ajv/dist/2020.js";
import type { TSchema } from "@sinclair/typebox";

const hasUniqueItemProperties = (properties: readonly string[], value: unknown): boolean => {
  if (!Array.isArray(value)) return false;
  const seen = new Set<string>();
  for (const item of value) {
    if (typeof item !== "object" || item === null) return false;
    const key = properties.map((property) => JSON.stringify((item as Record<string, unknown>)[property])).join("\u0000");
    if (seen.has(key)) return false;
    seen.add(key);
  }
  return true;
};

const strictAjv = (): Ajv2020 => {
  const ajv = new Ajv2020({ strict: true, allErrors: true });
  // This is deliberately a validation keyword, not annotation: all internal
  // TypeBox/JSON-schema consumers use the same strict path.
  ajv.addKeyword({
    keyword: "uniqueItemProperties",
    type: "array",
    schemaType: "array",
    validate: hasUniqueItemProperties,
    errors: false,
  });
  return ajv;
};

/** TypeBox values are JSON Schema; this is the single strict 2020-12 validator path. */
const draft2020 = (value: unknown): unknown => {
  if (Array.isArray(value)) return value.map(draft2020);
  if (!value || typeof value !== "object") return value;
  const record = Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, draft2020(item)]));
  // TypeBox represents tuples with the draft-07 `items: []` form. Ajv's
  // 2020-12 validator rightly rejects that form; translate it before every
  // strict boundary check rather than silently skipping tuple validation.
  if (Array.isArray(record.items)) {
    record.prefixItems = record.items;
    delete record.items;
    // Draft-07's companion keyword becomes `items: false` in 2020-12.
    if (record.additionalItems === false) record.items = false;
    delete record.additionalItems;
  }
  return record;
};

export const asJsonSchema2020 = <T extends TSchema>(schema: T) => ({
  $schema: "https://json-schema.org/draft/2020-12/schema",
  ...(draft2020(schema) as Record<string, unknown>),
});

// Compilation is the expensive step and schemas are module-level constants:
// memoize per schema object. A 200-session run validates thousands of
// revisions; recompiling per call was pure overhead.
const compiledValidators = new WeakMap<TSchema, ReturnType<ReturnType<typeof strictAjv>["compile"]>>();
export const validateStrict = <T extends TSchema>(schema: T, value: unknown): value is T["static"] => {
  let validator = compiledValidators.get(schema);
  if (!validator) { validator = strictAjv().compile(asJsonSchema2020(schema)); compiledValidators.set(schema, validator); }
  return Boolean(validator(value));
};
