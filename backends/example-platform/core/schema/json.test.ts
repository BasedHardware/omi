import { expect, test } from "bun:test";
import { Type } from "@sinclair/typebox";
import { asJsonSchema2020, validateStrict } from "./json";

test("T0 TypeBox emits strict JSON Schema 2020-12 and validates", () => {
  const schema = Type.Object({ id: Type.String() }, { additionalProperties: false });
  expect(asJsonSchema2020(schema).$schema).toBe("https://json-schema.org/draft/2020-12/schema");
  expect(validateStrict(schema, { id: "fixture" })).toBe(true);
  expect(validateStrict(schema, { id: 7 })).toBe(false);
});
