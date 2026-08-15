// domain-pending(DIV-CHAT-SOURCE-001)

/**
 * Gateway self-description from `/ready`. This is the only input that may mint
 * a real-provider capability stamp: the gateway's own declared schema, and
 * `real_model_proxy: true` when the gateway says so. Missing schema, a failed
 * probe, or a body that does not declare the flag stays unknown. Reachability
 * is not treated as a real model.
 */

const SAFE_SCHEMA = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/u;
const SAFE_MODEL = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$/u;
const SAFE_ADAPTER = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/u;
export const UNKNOWN_GATEWAY_SCHEMA = "unknown" as const;
export const NONE_GATEWAY_KIND = "none" as const;

export interface GatewayEngineIdentity {
  readonly schema: string;
  readonly realModelProxy: boolean;
  readonly model: string | null;
}

export const UNKNOWN_GATEWAY_ENGINE_IDENTITY: GatewayEngineIdentity = Object.freeze({
  schema: UNKNOWN_GATEWAY_SCHEMA,
  realModelProxy: false,
  model: null,
});

export interface GatewayCapabilityStamp {
  readonly tier: "real-provider" | "unknown";
  readonly adapter: string;
  readonly deterministic: false;
}

const ownData = (input: unknown): Record<string, unknown> | null => {
  try {
    if (input === null || typeof input !== "object" || Array.isArray(input)) return null;
    const prototype = Object.getPrototypeOf(input);
    if (prototype !== Object.prototype && prototype !== null) return null;
    const descriptors = Object.getOwnPropertyDescriptors(input);
    const values: Record<string, unknown> = Object.create(null) as Record<string, unknown>;
    for (const key of Reflect.ownKeys(input)) {
      if (typeof key !== "string") return null;
      const descriptor = descriptors[key];
      if (descriptor === undefined || !("value" in descriptor)) return null;
      values[key] = descriptor.value;
    }
    return values;
  } catch {
    return null;
  }
};

/** Strict reader: a fake cannot set `realModelProxy` without the boolean flag. */
export const parseGatewayReadyBody = (input: unknown): GatewayEngineIdentity => {
  const record = ownData(input);
  if (record === null) return UNKNOWN_GATEWAY_ENGINE_IDENTITY;
  const schema = record.schema;
  if (typeof schema !== "string" || schema === UNKNOWN_GATEWAY_SCHEMA || !SAFE_SCHEMA.test(schema)) {
    return UNKNOWN_GATEWAY_ENGINE_IDENTITY;
  }
  const realModelProxy = record.real_model_proxy === true;
  const rawModel = record.model;
  const model = typeof rawModel === "string" && SAFE_MODEL.test(rawModel) ? rawModel : null;
  return Object.freeze({ schema, realModelProxy, model });
};

const readyUrl = (gatewayUrl: string): URL | null => {
  try {
    const parsed = new URL(gatewayUrl);
    if ((parsed.protocol !== "http:" && parsed.protocol !== "https:")
      || parsed.username.length > 0 || parsed.password.length > 0) {
      return null;
    }
    return new URL("/ready", parsed.origin);
  } catch {
    return null;
  }
};

export const probeGatewayEngineIdentity = async (
  gatewayUrl: string,
  options: { readonly fetch?: typeof fetch; readonly timeoutMs?: number } = {},
): Promise<GatewayEngineIdentity> => {
  const url = readyUrl(gatewayUrl);
  if (url === null) return UNKNOWN_GATEWAY_ENGINE_IDENTITY;
  try {
    const response = await (options.fetch ?? fetch)(url, {
      method: "GET",
      signal: AbortSignal.timeout(options.timeoutMs ?? 2_000),
    });
    if (!response.ok) return UNKNOWN_GATEWAY_ENGINE_IDENTITY;
    return parseGatewayReadyBody(await response.json());
  } catch {
    return UNKNOWN_GATEWAY_ENGINE_IDENTITY;
  }
};

export const bootGatewayKind = (identity: GatewayEngineIdentity | null): string =>
  identity === null ? NONE_GATEWAY_KIND : identity.schema;

export const bootGatewayModel = (identity: GatewayEngineIdentity | null): string | null =>
  identity === null ? null : identity.model;

/**
 * Closed capability field set: adapter, tier, deterministic.
 * `tier: "real-provider"` only when the gateway declared `real_model_proxy: true`
 * on a body that also carried a schema.
 */
export const stampForGatewayEngine = (
  identity: GatewayEngineIdentity,
  transport: "default" | "injected",
): GatewayCapabilityStamp => {
  if (identity.schema === UNKNOWN_GATEWAY_SCHEMA) {
    return Object.freeze({
      tier: "unknown",
      adapter: transport === "injected" ? "omi-llm-gateway-injected-transport" : "omi-llm-gateway",
      deterministic: false,
    });
  }
  const withModel = identity.model === null ? identity.schema : `${identity.schema}/${identity.model}`;
  const adapter = SAFE_ADAPTER.test(withModel) ? withModel : identity.schema;
  return Object.freeze({
    tier: identity.realModelProxy ? "real-provider" : "unknown",
    adapter,
    deterministic: false,
  });
};
