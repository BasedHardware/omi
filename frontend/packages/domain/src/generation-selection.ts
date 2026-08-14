/**
 * Per-domain backend generation selection, driven from OUTSIDE the code.
 *
 * Two backend generations now coexist: `legacy` (the old wire, through
 * `packages/adapters-legacy`) and `platform` (the contracts-native wire,
 * through `packages/adapters-platform`). Board ruling PR-1 puts memories on
 * the platform generation and leaves tasks, conversations and folders on
 * legacy tonight, because only the memory read path is ratified.
 *
 * The surfaces must not know which generation they are on — that is what the
 * `ProductionStores` ports are for. The SHELL knows, and it must be able to
 * say so without a recompile: David's stated goal is launching the macOS and
 * iOS apps against a local backend and using them, so the knob has to live in
 * host configuration (a launch argument, an injected config object, a query
 * string), not in a constant somebody edits and rebuilds.
 *
 * Everything here is therefore a pure function of UNTRUSTED input. A host
 * config is a file or an argv string a human typed; it is parsed and
 * validated, never trusted.
 *
 * THE DESIGN RULE THAT MATTERS: an unavailable request is REJECTED AND
 * REPORTED, never silently downgraded. A shell that believes it is exercising
 * the new backend while quietly running on the old one produces a night of
 * green tests that prove nothing — and that is the single most expensive
 * failure available to us tonight.
 */

export type BackendGeneration = "legacy" | "platform";

export type ProductionDomain = "memories" | "conversations" | "folders" | "tasks";

export const PRODUCTION_DOMAINS: readonly ProductionDomain[] = [
  "memories",
  "conversations",
  "folders",
  "tasks",
];

export type GenerationSelection = Readonly<Record<ProductionDomain, BackendGeneration>>;

/**
 * What each domain can ACTUALLY be served by. This is data about the state of
 * the migration, not a promise: a domain gains `platform` here on the day its
 * contract is ratified and its adapter passes that domain's fixtures, and not
 * before. Editing this table without both is how a shell ends up pointed at an
 * endpoint nobody wrote.
 */
export const PRODUCTION_GENERATION_AVAILABILITY: Readonly<
  Record<ProductionDomain, readonly BackendGeneration[]>
> = {
  // Ratified: @omi-core/ratified-contracts 0.1.1, memory READ path.
  memories: ["legacy", "platform"],
  // Not ratified. `adapters-legacy` only.
  conversations: ["legacy"],
  folders: ["legacy"],
  tasks: ["legacy"],
};

export const LEGACY_ONLY_GENERATION: GenerationSelection = {
  memories: "legacy",
  conversations: "legacy",
  folders: "legacy",
  tasks: "legacy",
};

/** Tonight's intended configuration, per board ruling PR-1. */
export const PLATFORM_MEMORIES_GENERATION: GenerationSelection = {
  memories: "platform",
  conversations: "legacy",
  folders: "legacy",
  tasks: "legacy",
};

export interface GenerationRejection {
  /**
   * The domain the request was about, or `null` when the host used a key that
   * is not a domain at all. `null` rather than a plausible-looking default:
   * attributing `nonsense=legacy` to `memories` would put a domain name in a
   * log line that the host never wrote, and the first thing anyone does with
   * that line is grep for the domain.
   */
  readonly domain: ProductionDomain | null;
  /** What the host asked for, echoed verbatim so a log shows the typo. */
  readonly requested: string;
  readonly reason: "unknown-domain" | "unknown-generation" | "generation-unavailable";
  readonly detail: string;
}

export interface ResolvedGenerationSelection {
  readonly selection: GenerationSelection;
  /**
   * Non-empty means the host asked for something it did not get. A shell MUST
   * surface this (log line, banner, non-zero exit in CI) rather than proceed
   * quietly — see the design rule in the file header.
   */
  readonly rejected: readonly GenerationRejection[];
}

/**
 * Resolve a host-supplied selection against what is actually available.
 *
 * Accepts `unknown` on purpose. The caller is handing us parsed JSON from a
 * config file, a `URLSearchParams` lookup, or an argv value — none of which
 * the type system has ever seen. Anything unrecognized becomes a rejection
 * with the requested value echoed, and the corresponding domain falls back to
 * `legacy`, which is the only generation guaranteed to serve every domain.
 */
export function resolveGenerationSelection(requested: unknown): ResolvedGenerationSelection {
  const rejected: GenerationRejection[] = [];
  const selection: Record<ProductionDomain, BackendGeneration> = { ...LEGACY_ONLY_GENERATION };

  if (requested === undefined || requested === null) return { selection, rejected };
  if (typeof requested !== "object" || Array.isArray(requested)) {
    return {
      selection,
      rejected: [
        {
          domain: null,
          requested: describe(requested),
          reason: "unknown-domain",
          detail: "generation selection must be an object keyed by domain name",
        },
      ],
    };
  }

  for (const [key, value] of Object.entries(requested as Record<string, unknown>)) {
    if (!isProductionDomain(key)) {
      rejected.push({
        domain: null,
        requested: key,
        reason: "unknown-domain",
        detail: `"${key}" is not a production domain (${PRODUCTION_DOMAINS.join(", ")})`,
      });
      continue;
    }
    if (!isBackendGeneration(value)) {
      rejected.push({
        domain: key,
        requested: describe(value),
        reason: "unknown-generation",
        detail: `"${describe(value)}" is not a backend generation (legacy, platform)`,
      });
      continue;
    }
    const available = PRODUCTION_GENERATION_AVAILABILITY[key];
    if (!available.includes(value)) {
      rejected.push({
        domain: key,
        requested: value,
        reason: "generation-unavailable",
        detail: `${key} has no ${value} generation yet; available: ${available.join(", ")}. Falling back to legacy — this run is NOT exercising the ${value} backend for ${key}.`,
      });
      continue;
    }
    selection[key] = value;
  }

  return { selection, rejected };
}

/**
 * Parse a selection out of a flat string map — the shape a launcher actually
 * has: environment variables, `--generation.memories=platform` argv pairs, or
 * a query string.
 *
 * Recognized keys are `generation.<domain>` and the bare `<domain>`, so a host
 * can namespace or not. `generations=platform` (no domain) is the shorthand
 * for "every domain that HAS this generation uses it" — which today means
 * memories only, and which reports a rejection for nothing, because asking for
 * the best available is not the same as asking for something unavailable.
 */
export function parseGenerationSelectionFromEntries(
  entries: Iterable<readonly [string, string]>,
): ResolvedGenerationSelection {
  const requested: Record<string, string> = {};
  let broadcast: string | null = null;

  for (const [rawKey, rawValue] of entries) {
    const key = rawKey.trim();
    const value = rawValue.trim();
    if (key === "generation" || key === "generations") {
      broadcast = value;
      continue;
    }
    const domain = key.startsWith("generation.") ? key.slice("generation.".length) : key;
    if (isProductionDomain(domain)) requested[domain] = value;
  }

  if (broadcast !== null && isBackendGeneration(broadcast)) {
    for (const domain of PRODUCTION_DOMAINS) {
      // Broadcast never overrides an explicit per-domain key, and never asks
      // for a generation the domain does not have — a blanket "use platform"
      // is a preference, not an assertion about every domain.
      if (requested[domain] === undefined && PRODUCTION_GENERATION_AVAILABILITY[domain].includes(broadcast)) {
        requested[domain] = broadcast;
      }
    }
  } else if (broadcast !== null) {
    const resolved = resolveGenerationSelection(requested);
    return {
      selection: resolved.selection,
      rejected: [
        ...resolved.rejected,
        {
          domain: null,
          requested: broadcast,
          reason: "unknown-generation",
          detail: `"${broadcast}" is not a backend generation (legacy, platform)`,
        },
      ],
    };
  }

  return resolveGenerationSelection(requested);
}

/** One line per rejection, for a shell to log. Empty array when all is well. */
export function describeGenerationRejections(
  rejected: readonly GenerationRejection[],
): readonly string[] {
  return rejected.map(
    (r) => `generation selection rejected [${r.reason}] ${r.domain ?? "<not-a-domain>"}=${r.requested}: ${r.detail}`,
  );
}

function isProductionDomain(value: string): value is ProductionDomain {
  return (PRODUCTION_DOMAINS as readonly string[]).includes(value);
}

function isBackendGeneration(value: unknown): value is BackendGeneration {
  return value === "legacy" || value === "platform";
}

function describe(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null) return "null";
  if (value === undefined) return "undefined";
  if (typeof value === "object") return Array.isArray(value) ? "array" : "object";
  return String(value);
}
