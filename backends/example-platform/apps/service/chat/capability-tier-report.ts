// domain-pending(DIV-CHAT-SOURCE-001)

/**
 * Machine-readable harness tiers. These names describe the evidence boundary,
 * not a model or provider. In particular, a local gateway route is not proof
 * that a provider was contacted and a deterministic adapter is never a real
 * agent success.
 */
export const AGENT_HARNESS_TIER_REPORT_SCHEMA_VERSION = 1 as const;

export const AGENT_HARNESS_CAPABILITY_TIERS = Object.freeze([
  "pure-contract",
  "deterministic-adapter",
  "local-integration",
  "native-consumer",
  "optional-provider-eval",
] as const);

export type AgentHarnessCapabilityTier = typeof AGENT_HARNESS_CAPABILITY_TIERS[number];

export const AGENT_HARNESS_PROVIDER_EVIDENCE = Object.freeze([
  "none",
  "gateway-routed",
  "provider-observed",
] as const);

export type AgentHarnessProviderEvidence = typeof AGENT_HARNESS_PROVIDER_EVIDENCE[number];
export type AgentHarnessTierOutcome = "not-evaluated" | "passed" | "failed";
export type LegacyChatCapabilityTier = "deterministic-scripted" | "real-provider" | "unknown";

/**
 * A tier report is deliberately narrower than a provider receipt. `claimsRealAgentSuccess`
 * is derived/validated against the tier and evidence, so a fake cannot set it
 * while still producing a parseable report.
 */
export interface AgentHarnessTierReport {
  readonly schemaVersion: typeof AGENT_HARNESS_TIER_REPORT_SCHEMA_VERSION;
  readonly tier: AgentHarnessCapabilityTier;
  readonly adapter: string;
  readonly deterministic: boolean;
  readonly providerEvidence: AgentHarnessProviderEvidence;
  readonly outcome: AgentHarnessTierOutcome;
  readonly claimsRealAgentSuccess: boolean;
  /** Wire-level assertion that deterministic/fake evidence cannot claim real success. */
  readonly fakeSuccessClaimsForbidden: true;
}

export interface AgentHarnessTierReportInput {
  readonly tier: AgentHarnessCapabilityTier;
  readonly adapter: string;
  readonly deterministic: boolean;
  readonly providerEvidence: AgentHarnessProviderEvidence;
  readonly outcome: AgentHarnessTierOutcome;
  readonly claimsRealAgentSuccess?: boolean;
}

const SAFE_ADAPTER = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$/u;
const REPORT_KEYS = Object.freeze([
  "adapter",
  "claimsRealAgentSuccess",
  "deterministic",
  "fakeSuccessClaimsForbidden",
  "outcome",
  "providerEvidence",
  "schemaVersion",
  "tier",
] as const);
const LEGACY_KEYS = Object.freeze(["adapter", "deterministic", "tier"] as const);

const hasExactOwnDataKeys = (value: object, keys: readonly string[]): boolean => {
  try {
    const ownKeys = Reflect.ownKeys(value);
    return ownKeys.length === keys.length
      && ownKeys.every((key) => typeof key === "string" && keys.includes(key))
      && keys.every((key) => ownKeys.includes(key));
  } catch {
    return false;
  }
};

const ownDataValue = (value: object, key: string): unknown => {
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const descriptor = descriptors[key];
  if (descriptor === undefined || !("value" in descriptor)) throw new TypeError("accessor or proxy");
  return descriptor.value;
};

const isTier = (value: unknown): value is AgentHarnessCapabilityTier =>
  typeof value === "string" && (AGENT_HARNESS_CAPABILITY_TIERS as readonly string[]).includes(value);
const isProviderEvidence = (value: unknown): value is AgentHarnessProviderEvidence =>
  typeof value === "string" && (AGENT_HARNESS_PROVIDER_EVIDENCE as readonly string[]).includes(value);
const isOutcome = (value: unknown): value is AgentHarnessTierOutcome =>
  value === "not-evaluated" || value === "passed" || value === "failed";

/**
 * Tier-specific safety invariants. Gateway routing remains an integration
 * observation only; provider-observed evidence is reserved for the optional
 * provider-evaluation lane.
 */
const isSafeTierReport = (input: AgentHarnessTierReportInput): boolean => {
  if (!isTier(input.tier) || !isProviderEvidence(input.providerEvidence) || !isOutcome(input.outcome)
    || typeof input.adapter !== "string" || !SAFE_ADAPTER.test(input.adapter)
    || typeof input.deterministic !== "boolean") return false;
  const claimsRealAgentSuccess = input.claimsRealAgentSuccess ?? false;
  if (typeof claimsRealAgentSuccess !== "boolean") return false;
  if (input.tier === "pure-contract" && input.providerEvidence !== "none") return false;
  if (input.tier === "deterministic-adapter"
    && (!input.deterministic || input.providerEvidence !== "none")) return false;
  if (input.tier === "local-integration"
    && input.providerEvidence === "provider-observed") return false;
  if (input.tier === "native-consumer"
    && input.providerEvidence === "provider-observed") return false;
  if (input.tier === "optional-provider-eval"
    && input.providerEvidence !== "provider-observed"
    && claimsRealAgentSuccess) return false;
  if (input.deterministic && input.providerEvidence === "provider-observed") return false;
  if (claimsRealAgentSuccess
    && (input.tier !== "optional-provider-eval"
      || input.providerEvidence !== "provider-observed"
      || input.deterministic
      || input.outcome !== "passed")) return false;
  return true;
};

const canonicalReport = (input: AgentHarnessTierReportInput): AgentHarnessTierReport => {
  if (!isSafeTierReport(input)) throw new TypeError("invalid agent harness tier report");
  return Object.freeze({
    schemaVersion: AGENT_HARNESS_TIER_REPORT_SCHEMA_VERSION,
    tier: input.tier,
    adapter: input.adapter,
    deterministic: input.deterministic,
    providerEvidence: input.providerEvidence,
    outcome: input.outcome,
    claimsRealAgentSuccess: input.claimsRealAgentSuccess ?? false,
    fakeSuccessClaimsForbidden: true,
  });
};

export const createAgentHarnessTierReport = (
  input: AgentHarnessTierReportInput,
): AgentHarnessTierReport => canonicalReport(input);

/**
 * Strict reader for persisted/exported reports. It rejects accessors,
 * inherited fields, extra keys, malformed versions, and fake success claims.
 */
export const parseAgentHarnessTierReport = (
  input: unknown,
): AgentHarnessTierReport | null => {
  try {
    const prototype = input !== null && typeof input === "object" ? Object.getPrototypeOf(input) : null;
    if (input === null || typeof input !== "object" || Array.isArray(input)
      || (prototype !== Object.prototype && prototype !== null)
      || !hasExactOwnDataKeys(input, REPORT_KEYS)) return null;
    const candidate: AgentHarnessTierReportInput & {
      readonly schemaVersion?: unknown;
      readonly fakeSuccessClaimsForbidden?: unknown;
    } = {
      tier: ownDataValue(input, "tier") as AgentHarnessCapabilityTier,
      adapter: ownDataValue(input, "adapter") as string,
      deterministic: ownDataValue(input, "deterministic") as boolean,
      providerEvidence: ownDataValue(input, "providerEvidence") as AgentHarnessProviderEvidence,
      outcome: ownDataValue(input, "outcome") as AgentHarnessTierOutcome,
      claimsRealAgentSuccess: ownDataValue(input, "claimsRealAgentSuccess") as boolean,
      fakeSuccessClaimsForbidden: ownDataValue(input, "fakeSuccessClaimsForbidden") as true,
      schemaVersion: ownDataValue(input, "schemaVersion"),
    };
    if (candidate.schemaVersion !== AGENT_HARNESS_TIER_REPORT_SCHEMA_VERSION) return null;
    if (candidate.fakeSuccessClaimsForbidden !== true) return null;
    return isSafeTierReport(candidate)
      ? canonicalReport(candidate)
      : null;
  } catch {
    return null;
  }
};

export const serializeAgentHarnessTierReport = (report: AgentHarnessTierReport): string => {
  const parsed = parseAgentHarnessTierReport(report);
  if (parsed === null) throw new TypeError("invalid agent harness tier report");
  return JSON.stringify(parsed);
};

export interface LegacyChatCapabilityReceipt {
  readonly tier: LegacyChatCapabilityTier;
  readonly adapter: string;
  readonly deterministic: boolean;
}

const isLegacyCapability = (value: unknown): value is LegacyChatCapabilityReceipt => {
  try {
    const prototype = value !== null && typeof value === "object" ? Object.getPrototypeOf(value) : null;
    if (value === null || typeof value !== "object" || Array.isArray(value)
      || (prototype !== Object.prototype && prototype !== null)
      || !hasExactOwnDataKeys(value, LEGACY_KEYS)) return false;
    const tier = ownDataValue(value, "tier");
    const adapter = ownDataValue(value, "adapter");
    const deterministic = ownDataValue(value, "deterministic");
    return (tier === "deterministic-scripted" || tier === "real-provider" || tier === "unknown")
      && typeof adapter === "string" && SAFE_ADAPTER.test(adapter)
      && typeof deterministic === "boolean"
      && (tier === "deterministic-scripted" ? deterministic : !deterministic);
  } catch {
    return false;
  }
};

/**
 * Bridges the legacy source receipt into the named harness tiers without
 * changing the old wire/event field. A gateway route is intentionally only a
 * local-integration observation; it never becomes provider success proof.
 */
export const reportForLegacyChatCapability = (
  capability: unknown,
  outcome: AgentHarnessTierOutcome = "not-evaluated",
): AgentHarnessTierReport => {
  if (!isLegacyCapability(capability)) {
    return canonicalReport({
      tier: "pure-contract",
      adapter: "unreported",
      deterministic: false,
      providerEvidence: "none",
      outcome,
      claimsRealAgentSuccess: false,
    });
  }
  if (capability.tier === "deterministic-scripted") {
    return canonicalReport({
      tier: "deterministic-adapter",
      adapter: capability.adapter,
      deterministic: true,
      providerEvidence: "none",
      outcome,
      claimsRealAgentSuccess: false,
    });
  }
  if (capability.tier === "real-provider") {
    return canonicalReport({
      tier: "local-integration",
      adapter: capability.adapter,
      deterministic: false,
      providerEvidence: "gateway-routed",
      outcome,
      claimsRealAgentSuccess: false,
    });
  }
  return canonicalReport({
    tier: "pure-contract",
    adapter: capability.adapter,
    deterministic: false,
    providerEvidence: "none",
    outcome,
    claimsRealAgentSuccess: false,
  });
};
