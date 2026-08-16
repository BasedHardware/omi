/**
 * Per-domain backend generation selection, driven from OUTSIDE the code.
 *
 * One backend generation remains: `platform` (the contracts-native wire,
 * through `packages/adapters-platform`). Memories, conversations, folders,
 * and tasks are ratified on platform. David's 2026-08-16 ruling retired the
 * legacy generation entirely — there is no fallback wire.
 *
 * The surfaces must not know which generation they are on — that is what the
 * `ProductionStores` ports are for. The SHELL knows, and it must be able to
 * say so without a recompile: the knob lives in host configuration (a launch
 * argument, an injected config object, a query string), not in a constant
 * somebody edits and rebuilds.
 *
 * Everything here is therefore a pure function of UNTRUSTED input. A host
 * config is a file or an argv string a human typed; it is parsed and
 * validated, never trusted.
 *
 * THE DESIGN RULE THAT MATTERS: an unavailable request is REJECTED AND
 * REPORTED, never silently downgraded. A shell that believes it is exercising
 * a generation nothing can serve, while quietly running on another, produces
 * a night of green tests that prove nothing.
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
 * the migration, not a promise. Editing this table without a serving adapter
 * is how a shell ends up pointed at an endpoint nobody wrote.
 *
 * `legacy` is gone: nothing in this tree can serve it. Requesting it is a
 * rejection that names the domain and the generation, not a silent fallback.
 */
export const PRODUCTION_GENERATION_AVAILABILITY: Readonly<
  Record<ProductionDomain, readonly BackendGeneration[]>
> = {
  memories: ["platform"],
  conversations: ["platform"],
  folders: ["platform"],
  tasks: ["platform"],
};

/** The only generation that can still be served, on every production domain. */
export const PLATFORM_ONLY_GENERATION: GenerationSelection = {
  memories: "platform",
  conversations: "platform",
  folders: "platform",
  tasks: "platform",
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
 * with the requested value echoed. An unavailable generation is refused and
 * reported; the corresponding domain stays on the only generation that can
 * serve it. There is no silent fallback onto a retired wire.
 */
export function resolveGenerationSelection(requested: unknown): ResolvedGenerationSelection {
  const rejected: GenerationRejection[] = [];
  const selection: Record<ProductionDomain, BackendGeneration> = { ...PLATFORM_ONLY_GENERATION };

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
        detail:
          `${key} has no ${value} generation; available: ${available.join(", ")}. `
          + `Refusing to serve ${value} for ${key} — this run is NOT exercising the ${value} backend.`,
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
 * for "every domain uses this generation" — and a blanket request for a
 * generation a domain cannot serve is rejected per domain, never skipped as a
 * preference. Skipping an unavailable broadcast was the silent fallback this
 * function exists to forbid.
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
      // Broadcast never overrides an explicit per-domain key. It DOES ask
      // every other domain for the broadcast generation, so an unavailable
      // blanket value is rejected by name rather than silently skipped.
      if (requested[domain] === undefined) requested[domain] = broadcast;
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
