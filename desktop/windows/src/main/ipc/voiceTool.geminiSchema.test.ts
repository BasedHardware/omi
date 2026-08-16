import { describe, it, expect } from 'vitest'
import { buildVoiceHubToolCatalog } from './voiceTool'
import {
  sanitizeGeminiToolSchema,
  GEMINI_SUPPORTED_SCHEMA_KEYS
} from '../../renderer/src/lib/voice/hub/geminiToolSchema'

// CI guard for the fast-close root cause: the REAL host tool catalog is advertised to
// Gemini Live, whose function-declaration `parameters` is an OpenAPI-3.0 Schema that rejects
// `additionalProperties` (which the catalog stamps on every tool). geminiHubSession runs each
// schema through `sanitizeGeminiToolSchema` before the wire; these tests pin that the real
// catalog stays Gemini-clean and that any FUTURE manifest keyword breaks CI here — not prod
// sockets. (The session-wiring half — that GeminiHubSession actually applies the sanitizer —
// lives in the renderer test geminiHubSession.test.ts.)

// JSON-Schema keywords we deliberately DROP because Gemini's Schema doesn't accept them. A
// raw manifest keyword that is neither supported nor in this set is unrecognized drift → a
// human must decide whether Gemini supports it (add to the allowlist) or it should be
// stripped (add here). This is the mechanism that turns a future manifest keyword into a CI
// failure instead of a dead prod socket.
const KNOWN_STRIPPED_KEYS = new Set([
  'additionalProperties',
  'unevaluatedProperties',
  '$schema',
  '$id',
  '$anchor',
  '$ref',
  '$defs',
  '$comment',
  'definitions',
  'oneOf',
  'allOf',
  'not',
  'const',
  'patternProperties',
  'propertyNames',
  'dependentSchemas',
  'dependentRequired',
  'dependencies',
  'if',
  'then',
  'else',
  'prefixItems',
  'contains',
  'minContains',
  'maxContains'
])

/** Walk a schema structurally, invoking `visit(key)` on every SCHEMA-LEVEL key (the keys
 *  under `properties` are property NAMES / data and are exempt), recursing only where a
 *  sub-schema actually lives. Mirrors the sanitizer's structure. */
function walkSchemaKeys(schema: unknown, visit: (key: string) => void): void {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) return
  for (const [key, value] of Object.entries(schema as Record<string, unknown>)) {
    visit(key)
    if (key === 'properties' && value && typeof value === 'object' && !Array.isArray(value)) {
      for (const sub of Object.values(value as Record<string, unknown>)) walkSchemaKeys(sub, visit)
    } else if (key === 'items') {
      walkSchemaKeys(value, visit)
    } else if (key === 'anyOf' && Array.isArray(value)) {
      for (const v of value) walkSchemaKeys(v, visit)
    }
    // enum / required / default / example / const are data — not descended into.
  }
}

describe('voice hub tool catalog — Gemini schema safety (real catalog)', () => {
  for (const role of ['coordinator', 'leaf'] as const) {
    it(`sanitizes every ${role} tool schema to zero non-allowlisted keywords`, () => {
      const catalog = buildVoiceHubToolCatalog(role)
      expect(catalog.length).toBeGreaterThan(0) // sanity: a real, non-empty catalog

      const offenders: string[] = []
      for (const tool of catalog) {
        const clean = sanitizeGeminiToolSchema(tool.parameters)
        walkSchemaKeys(clean, (key) => {
          if (!GEMINI_SUPPORTED_SCHEMA_KEYS.has(key)) offenders.push(`${tool.name}: ${key}`)
        })
      }
      expect(offenders).toEqual([])
    })

    it(`only sees known keywords in the raw ${role} catalog (fails on unrecognized manifest drift)`, () => {
      const catalog = buildVoiceHubToolCatalog(role)
      const unknown = new Set<string>()
      for (const tool of catalog) {
        walkSchemaKeys(tool.parameters, (key) => {
          if (!GEMINI_SUPPORTED_SCHEMA_KEYS.has(key) && !KNOWN_STRIPPED_KEYS.has(key)) {
            unknown.add(`${tool.name}: ${key}`)
          }
        })
      }
      // A brand-new JSON-Schema keyword in the manifest lands here — decide: allowlist it
      // (Gemini supports it) or add it to KNOWN_STRIPPED_KEYS.
      expect([...unknown]).toEqual([])
    })
  }

  it('is load-bearing: the raw catalog carries additionalProperties, the sanitized one does not', () => {
    const catalog = buildVoiceHubToolCatalog('coordinator')
    const rawHasAdditionalProps = catalog.some((t) =>
      JSON.stringify(t.parameters ?? {}).includes('"additionalProperties"')
    )
    expect(rawHasAdditionalProps).toBe(true) // guards against a no-op test if the manifest changes
    const cleanedHasAdditionalProps = catalog.some((t) =>
      JSON.stringify(sanitizeGeminiToolSchema(t.parameters)).includes('"additionalProperties"')
    )
    expect(cleanedHasAdditionalProps).toBe(false)
  })
})
