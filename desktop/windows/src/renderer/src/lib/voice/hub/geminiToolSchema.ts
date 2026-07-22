// Gemini Live tool-schema sanitizer — a dependency-free leaf so BOTH the renderer hub
// lane (geminiHubSession) and a main-side catalog test can import it without dragging in
// pcmPlayer/AudioWorklet or the agent-kernel graph.
//
// Gemini Live's function-declaration `parameters` is an OpenAPI-3.0 `Schema`, NOT full
// JSON Schema. Any keyword outside this Schema subset — most notably `additionalProperties`,
// which the host tool catalog stamps on every tool — makes Gemini REJECT the whole
// BidiGenerateContent setup and close the socket within seconds of connect (no
// `setupComplete`), so every warm silently cascades and the reconnect budget bleeds out.
// (Full JSON Schema is only accepted in Gemini's separate `parameters_json_schema` field,
// which the raw Bidi setup frame does not use.) We ALLOWLIST the supported Schema keys and
// drop everything else — fail-closed, so a future manifest keyword can't reach the wire and
// silently kill sockets again. OpenAI's realtime lane REQUIRES `additionalProperties:false`
// for strict tools, so this stripping is Gemini-only (openaiHubSession passes the schema
// through). Field set per the `@google/genai` `Schema` type (verified via Context7).
export const GEMINI_SUPPORTED_SCHEMA_KEYS: ReadonlySet<string> = new Set([
  'type',
  'format',
  'title',
  'description',
  'nullable',
  'default',
  'enum',
  'items',
  'minItems',
  'maxItems',
  'properties',
  'required',
  'minProperties',
  'maxProperties',
  'minimum',
  'maximum',
  'minLength',
  'maxLength',
  'pattern',
  'example',
  'anyOf',
  'propertyOrdering'
])

/** Project a JSON Schema onto Gemini's OpenAPI-3.0 `Schema` subset: keep only the
 *  allowlisted keys and recurse structurally (into `properties` values — NOT their
 *  arbitrary names — plus `items` and `anyOf`). Non-schema-bearing values (`enum`,
 *  `required`, `default`, `example`, …) are copied verbatim. Pure (returns a fresh deep
 *  copy; never mutates the input, so a catalog object can be shared across provider
 *  lanes). */
export function sanitizeGeminiToolSchema(schema: unknown): unknown {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) return schema
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(schema as Record<string, unknown>)) {
    if (!GEMINI_SUPPORTED_SCHEMA_KEYS.has(key)) continue // fail-closed: drop unknown keyword
    if (key === 'properties' && value && typeof value === 'object' && !Array.isArray(value)) {
      // A map of property-NAME → sub-schema: keep every name, sanitize each sub-schema.
      const props: Record<string, unknown> = {}
      for (const [name, sub] of Object.entries(value as Record<string, unknown>)) {
        props[name] = sanitizeGeminiToolSchema(sub)
      }
      out[key] = props
    } else if (key === 'items') {
      out[key] = sanitizeGeminiToolSchema(value)
    } else if (key === 'anyOf' && Array.isArray(value)) {
      out[key] = value.map(sanitizeGeminiToolSchema)
    } else {
      out[key] = value // scalar / enum / required / example / default — verbatim
    }
  }
  return out
}
