import Ajv2020 from "ajv/dist/2020.js";
import type { TSchema } from "@sinclair/typebox";

/** TypeBox values are JSON Schema; this is the single strict 2020-12 validator path. */
export const asJsonSchema2020 = <T extends TSchema>(schema: T) => ({
  $schema: "https://json-schema.org/draft/2020-12/schema",
  ...schema,
});

export const validateStrict = <T extends TSchema>(schema: T, value: unknown): value is T["static"] => {
  const ajv = new Ajv2020({ strict: true, allErrors: true });
  return Boolean(ajv.compile(asJsonSchema2020(schema))(value));
};
