/**
 * The OpenAPI-generated PlanType is intentionally a closed union. The server
 * can add a value before this client is regenerated, though, so all runtime
 * plan decisions must pass through this boundary first.
 */
export const CATALOG_PLAN_IDS = [
  'basic',
  'plus',
  'unlimited',
  'unlimited_v2',
  'operator',
  'architect'
] as const

export type CatalogPlanId = (typeof CATALOG_PLAN_IDS)[number]

const CATALOG_PLAN_ID_SET: ReadonlySet<string> = new Set(CATALOG_PLAN_IDS)

/** The legacy wire value is an alias, not another catalog identity. */
const LEGACY_PLAN_ALIASES = new Map<string, CatalogPlanId>([['pro', 'architect']])

export type DecodedPlan =
  | { readonly kind: 'known'; readonly id: CatalogPlanId; readonly raw: string }
  | { readonly kind: 'unknown'; readonly raw: string }

export const UNKNOWN_PLAN_TITLE = 'Plan unavailable'
export const UNKNOWN_PLAN_SUBTITLE = 'Your plan details are unavailable.'

/**
 * Decode a plan without allowing a stale generated union to turn a new plan
 * into Basic. Known aliases retain their raw spelling for a lossless response
 * round-trip; capability decisions use the canonical catalog id.
 */
export function decodePlan(raw: unknown): DecodedPlan | undefined {
  if (typeof raw !== 'string') return undefined

  if (CATALOG_PLAN_ID_SET.has(raw)) {
    return { kind: 'known', id: raw as CatalogPlanId, raw }
  }

  const alias = LEGACY_PLAN_ALIASES.get(raw)
  if (alias !== undefined) return { kind: 'known', id: alias, raw }

  return { kind: 'unknown', raw }
}

/** Alias for call sites that describe this boundary as parsing. */
export const parsePlan = decodePlan

/** Re-encode without losing an alias or an unrecognised future value. */
export function encodePlan(plan: DecodedPlan | undefined): string | undefined {
  return plan?.raw
}

/** Alias for wire-facing call sites. */
export const serializePlan = encodePlan

function asDecodedPlan(value: unknown): DecodedPlan | undefined {
  if (
    typeof value === 'object' &&
    value !== null &&
    'kind' in value &&
    'raw' in value &&
    (value.kind === 'known' || value.kind === 'unknown') &&
    typeof value.raw === 'string'
  ) {
    // Do not trust a caller-provided discriminant or canonical id. Re-parse
    // the raw wire value so forged/stale objects cannot acquire capability.
    return decodePlan(value.raw)
  }
  return decodePlan(value)
}

/** Return a canonical catalog id, or undefined for absent/unknown values. */
export function canonicalPlanId(value: unknown): CatalogPlanId | undefined {
  const decoded = asDecodedPlan(value)
  return decoded?.kind === 'known' ? decoded.id : undefined
}

const PAID_PLAN_IDS: ReadonlySet<CatalogPlanId> = new Set([
  'plus',
  'unlimited',
  'unlimited_v2',
  'operator',
  'architect'
])

/** Unknown values never acquire paid capability by default. */
export function isPaidPlanValue(value: unknown): boolean {
  const id = canonicalPlanId(value)
  return id !== undefined && PAID_PLAN_IDS.has(id)
}

const PLAN_DISPLAY_NAMES: Readonly<Record<CatalogPlanId, string>> = {
  basic: 'Free',
  plus: 'Plus',
  unlimited: 'Neo',
  unlimited_v2: 'Unlimited',
  operator: 'Operator',
  architect: 'Architect'
}

/** Neutral copy for unknown values; never call them Free/Basic. */
export function planDisplayName(value: unknown): string {
  const id = canonicalPlanId(value)
  return id === undefined ? UNKNOWN_PLAN_TITLE : PLAN_DISPLAY_NAMES[id]
}

/**
 * Parse any billing response whose nested subscription carries a plan. The
 * returned object keeps the generated DTO shape for existing renderer callers,
 * while guaranteeing that aliases and unknown strings are not rewritten.
 */
export function parsePlanResponse<T extends { subscription?: { plan?: unknown } }>(response: T): T {
  const subscription = response?.subscription
  if (!subscription || typeof subscription !== 'object') return response

  const decoded = decodePlan(subscription.plan)
  if (!decoded) return response

  return {
    ...response,
    subscription: {
      ...subscription,
      plan: encodePlan(decoded)
    }
  } as T
}
