// Tool ↔ instruction coverage guard — a mechanical check against a whole bug
// class we hit repeatedly on the Windows port:
//
//   A tool is ADVERTISED to a model surface (it appears in that surface's tool
//   catalog / manifest projection) but the surface's SYSTEM PROMPT / INSTRUCTION
//   never NAMES it or says when to use it — so the model, especially a realtime
//   voice model, never reaches for it and the capability silently no-ops.
//
// The rule this module encodes: for every model surface, every tool advertised to
// that surface must be NAMED in that surface's assembled instruction text (or be
// on a small, documented `allow` list — the `guard:allow` escape hatch).
//
// This module is the PURE analysis core: types + pure functions over plain data.
// It imports no manifest, no kernel, no Electron, no renderer — the caller (the
// vitest guard, `toolInstructionCoverage.test.ts`) derives each surface's real
// advertised-tool list and instruction text from the production code and injects
// them here. That keeps the rule independently unit-testable and keeps this file
// importable anywhere, while the binding to real surfaces lives in the test.
//
// ENFORCEMENT is per-surface and staged, because the instruction-side content is
// landing on sibling branches (feat/win-voice-instruction-tools,
// feat/win-chat-initiative-routing) that this branch is not based on:
//   * 'enforced' — a gap FAILS the guard. Use once a surface's prose names tools.
//   * 'pending'  — a gap is REPORTED (owner noted) but does not fail, so the guard
//                  can ship green before the sibling branches land. Anti-rot: a
//                  'pending' surface that becomes FULLY covered fails with
//                  "flip me to enforced", so the exception cannot silently outlive
//                  its purpose.

/** How strictly a surface's coverage gaps are treated (see file header). */
export type SurfaceEnforcement = 'enforced' | 'pending'

/** One model surface's inputs: what it advertises and what its instruction says. */
export interface SurfaceCoverageInput {
  /** Human-readable surface id, e.g. 'realtime_voice' or 'desktopChat'. */
  surface: string
  /** Canonical names of the tools actually advertised to this surface. Derived by
   *  the caller from the production catalog/manifest — never hand-listed. */
  advertisedTools: readonly string[]
  /** Optional per-tool aliases the prose may legitimately use instead of the
   *  canonical name (e.g. semantic_search → search_screen_history). */
  aliasesByTool?: Readonly<Record<string, readonly string[]>>
  /** The surface's assembled instruction/prompt text. `present:false` when this
   *  branch has no builder for it yet (module lands on a sibling branch). */
  instruction: { present: boolean; text?: string }
  enforcement: SurfaceEnforcement
  /** For a 'pending' surface or an absent instruction: who is expected to close
   *  the gap (a branch name / short reason). Surfaced in the report. */
  pendingOwner?: string
  /** `guard:allow` — tools intentionally NOT named in this surface's prose, keyed
   *  to a required human reason. Permanently exempt from the coverage rule. */
  allow?: Readonly<Record<string, string>>
  /** The universe of real tool names (the full manifest) used for the REVERSE
   *  check: an instruction that names a real tool NOT advertised to this surface
   *  makes the model promise work it cannot do. Omit to skip the reverse check. */
  knownToolNames?: readonly string[]
}

export type SurfaceCoverageStatus =
  | 'ok' // enforced + every advertised tool named
  | 'pending' // pending + still has gaps (reported, not failed)
  | 'instruction-missing' // no instruction builder on this branch (reported)
  | 'violation' // enforced + at least one advertised tool unnamed (FAILS)
  | 'pending-stale' // pending but fully covered — flip to enforced (FAILS)

export interface SurfaceCoverageResult {
  surface: string
  status: SurfaceCoverageStatus
  enforcement: SurfaceEnforcement
  advertisedCount: number
  /** Advertised tools whose name (or an alias) appears in the instruction. */
  mentioned: string[]
  /** Advertised tools that are unnamed AND not on the allow list. */
  missing: string[]
  /** REVERSE: real tool names the instruction references that are NOT advertised
   *  to this surface (and not allow-listed) — the model is told about a tool it
   *  cannot call. Empty when no instruction text or no `knownToolNames`. */
  referencedNotAdvertised: string[]
  /** Advertised tools skipped via `guard:allow`, with reasons echoed in `message`. */
  allowlisted: string[]
  pendingOwner?: string
  /** True when this result should fail the guard (`violation` or `pending-stale`). */
  fails: boolean
  message: string
}

/** Statuses that fail the guard. */
const FAILING_STATUSES: ReadonlySet<SurfaceCoverageStatus> = new Set<SurfaceCoverageStatus>([
  'violation',
  'pending-stale'
])

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** True when `name` appears in `text` as a standalone token (not merely a
 *  substring of a longer identifier — so `get_tasks` does not match
 *  `get_tasks_extended`). Tool names are snake_case, so this is robust. */
export function instructionMentions(text: string, name: string): boolean {
  if (!name) return false
  const pattern = new RegExp(`(^|[^A-Za-z0-9_])${escapeRegExp(name)}([^A-Za-z0-9_]|$)`)
  return pattern.test(text)
}

/** True when the tool's canonical name OR any of its aliases is named in `text`. */
function toolIsMentioned(
  text: string,
  tool: string,
  aliasesByTool?: Readonly<Record<string, readonly string[]>>
): boolean {
  if (instructionMentions(text, tool)) return true
  for (const alias of aliasesByTool?.[tool] ?? []) {
    if (instructionMentions(text, alias)) return true
  }
  return false
}

/** Analyze one surface's advertised-vs-mentioned coverage. Pure. */
export function analyzeSurfaceCoverage(input: SurfaceCoverageInput): SurfaceCoverageResult {
  const advertised = [...new Set(input.advertisedTools)]
  const allow = input.allow ?? {}
  const allowlisted = advertised.filter((tool) => tool in allow)
  const considered = advertised.filter((tool) => !(tool in allow))

  // No instruction builder on this branch: nothing to match against.
  if (!input.instruction.present) {
    const status: SurfaceCoverageStatus =
      input.enforcement === 'enforced' ? 'violation' : 'instruction-missing'
    return {
      surface: input.surface,
      status,
      enforcement: input.enforcement,
      advertisedCount: advertised.length,
      mentioned: [],
      missing: considered,
      referencedNotAdvertised: [],
      allowlisted,
      pendingOwner: input.pendingOwner,
      fails: FAILING_STATUSES.has(status),
      message:
        input.enforcement === 'enforced'
          ? `ENFORCED surface "${input.surface}" has no instruction builder on this branch — ` +
            `cannot verify ${considered.length} advertised tool(s).`
          : `No instruction builder for "${input.surface}" on this branch` +
            (input.pendingOwner ? ` (owner: ${input.pendingOwner})` : '') +
            `; ${considered.length} advertised tool(s) unverified.`
    }
  }

  const text = input.instruction.text ?? ''
  const mentioned = considered.filter((tool) => toolIsMentioned(text, tool, input.aliasesByTool))
  const missing = considered.filter((tool) => !toolIsMentioned(text, tool, input.aliasesByTool))

  // REVERSE: real tool names the prose references but the surface does not
  // advertise. Scan only KNOWN tool names (never arbitrary snake_case prose), so
  // it cannot false-positive on words like `about_user` or `screen_recording`.
  const advertisedSet = new Set(advertised)
  const referencedNotAdvertised = [...new Set(input.knownToolNames ?? [])].filter(
    (name) => !advertisedSet.has(name) && !(name in allow) && instructionMentions(text, name)
  )

  const clean = missing.length === 0 && referencedNotAdvertised.length === 0
  const problems: string[] = []
  if (missing.length > 0) problems.push(`unnamed advertised: ${missing.join(', ')}`)
  if (referencedNotAdvertised.length > 0) {
    problems.push(`referenced-but-not-advertised: ${referencedNotAdvertised.join(', ')}`)
  }

  let status: SurfaceCoverageStatus
  let message: string
  if (input.enforcement === 'enforced') {
    status = clean ? 'ok' : 'violation'
    message = clean
      ? `All ${considered.length} advertised tool(s) named; no phantom references.`
      : `Instruction coverage problems — ${problems.join('; ')}.`
  } else if (clean) {
    // Pending but nothing is missing or phantom — the sibling branch's work has
    // landed; the 'pending' marker is now stale and must be flipped to 'enforced'.
    status = 'pending-stale'
    message =
      `PENDING surface "${input.surface}" is now fully covered — set its enforcement to ` +
      `'enforced' and drop the pending owner${input.pendingOwner ? ` (${input.pendingOwner})` : ''}.`
  } else {
    status = 'pending'
    message = `PENDING (owner: ${input.pendingOwner ?? 'unassigned'}): ${problems.join('; ')}.`
  }

  return {
    surface: input.surface,
    status,
    enforcement: input.enforcement,
    advertisedCount: advertised.length,
    mentioned,
    missing,
    referencedNotAdvertised,
    allowlisted,
    pendingOwner: input.pendingOwner,
    fails: FAILING_STATUSES.has(status),
    message
  }
}

// ── Second surface of the SAME bug class: a tool's own advertised COPY ──────────
// The instruction-prose reverse-check above catches a system prompt that names an
// unadvertised tool. But a tool's DECLARATION also reaches the model: its
// description and its parameter descriptions. If an advertised tool's own copy tells
// the model to "prefer get_tasks" / "first call get_tasks" while get_tasks is not
// advertised to this surface, the model is pointed at a tool it cannot call — the
// exact bug that shipped in the voice manifest (update_action_item / get_action_items
// naming get_tasks). This is the parallel reverse-check over each advertised tool's
// model-facing copy. Same robustness rule: scan only KNOWN tool names, and treat a
// self-reference or a reference to ANOTHER advertised tool as fine.

/** One advertised tool's model-facing copy: its description plus every parameter
 *  description the surface hands the model. Derived by the caller straight from the
 *  advertised catalog declaration, so it never drifts from what the model sees. */
export interface AdvertisedToolCopy {
  name: string
  description: string
  parameterDescriptions: readonly string[]
}

export interface ToolCopyCoverageInput {
  surface: string
  /** Every tool advertised to this surface, with the copy the model reads for it. */
  advertised: readonly AdvertisedToolCopy[]
  /** The full manifest tool-name universe (the reverse-check needle set). */
  knownToolNames: readonly string[]
  /** `guard:allow` — known tool names an advertised tool's copy may reference though
   *  they are unadvertised here, keyed to a required human reason. */
  allow?: Readonly<Record<string, string>>
}

/** One offending advertised tool: the unadvertised known tools its copy names. */
export interface ToolCopyOffender {
  tool: string
  references: string[]
}

export interface ToolCopyCoverageResult {
  surface: string
  advertisedCount: number
  offenders: ToolCopyOffender[]
  fails: boolean
  message: string
}

/** Scan each advertised tool's own description + parameter descriptions for the name
 *  of a KNOWN tool that is NOT advertised to this surface (and not allow-listed) —
 *  a description that points the model at an uncallable tool. Pure. */
export function analyzeAdvertisedToolCopy(input: ToolCopyCoverageInput): ToolCopyCoverageResult {
  const advertisedNames = new Set(input.advertised.map((tool) => tool.name))
  const allow = input.allow ?? {}
  const known = [...new Set(input.knownToolNames)]
  const offenders: ToolCopyOffender[] = []

  for (const tool of input.advertised) {
    const copy = [tool.description, ...tool.parameterDescriptions].join('\n')
    const references = known.filter(
      (name) =>
        name !== tool.name && // a tool naming itself is fine
        !advertisedNames.has(name) && // naming another advertised tool is fine
        !(name in allow) &&
        instructionMentions(copy, name)
    )
    if (references.length > 0) offenders.push({ tool: tool.name, references })
  }

  const fails = offenders.length > 0
  return {
    surface: input.surface,
    advertisedCount: input.advertised.length,
    offenders,
    fails,
    message: fails
      ? `Advertised tools on "${input.surface}" whose copy names an unadvertised tool: ` +
        `${offenders.map((o) => `${o.tool} → ${o.references.join(', ')}`).join('; ')}.`
      : `No advertised tool on "${input.surface}" names an unadvertised tool in its copy ` +
        `(${input.advertised.length} scanned).`
  }
}

export interface CoverageReport {
  results: SurfaceCoverageResult[]
  /** Results that fail the guard (`violation` or `pending-stale`). */
  violations: SurfaceCoverageResult[]
  ok: boolean
}

/** Analyze every surface and collect the failing ones. Pure. */
export function analyzeToolInstructionCoverage(
  inputs: readonly SurfaceCoverageInput[]
): CoverageReport {
  const results = inputs.map(analyzeSurfaceCoverage)
  const violations = results.filter((result) => result.fails)
  return { results, violations, ok: violations.length === 0 }
}

/** Render a human-readable report — printed by the guard so the current gaps are
 *  always visible in `pnpm test` / `pnpm check:tool-instruction-coverage`. */
export function formatCoverageReport(report: CoverageReport): string {
  const lines: string[] = ['Tool ↔ instruction coverage:']
  for (const result of report.results) {
    const marker =
      result.status === 'ok'
        ? 'OK '
        : result.status === 'pending'
          ? '..'
          : result.status === 'instruction-missing'
            ? '--'
            : 'XX'
    lines.push(
      `  [${marker}] ${result.surface} (${result.enforcement}): ` +
        `${result.mentioned.length}/${result.advertisedCount} named` +
        (result.allowlisted.length ? `, ${result.allowlisted.length} allow` : '') +
        (result.referencedNotAdvertised.length
          ? `, ${result.referencedNotAdvertised.length} phantom`
          : '')
    )
    lines.push(`        ${result.message}`)
  }
  lines.push(report.ok ? 'Result: PASS' : `Result: FAIL (${report.violations.length} surface(s))`)
  return lines.join('\n')
}
