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

  let status: SurfaceCoverageStatus
  let message: string
  if (input.enforcement === 'enforced') {
    status = missing.length === 0 ? 'ok' : 'violation'
    message =
      missing.length === 0
        ? `All ${considered.length} advertised tool(s) are named in the instruction.`
        : `${missing.length} advertised tool(s) are NOT named in the instruction: ${missing.join(', ')}.`
  } else if (missing.length === 0) {
    // Pending but nothing is missing — the sibling branch's work has landed; the
    // 'pending' marker is now stale and must be flipped to 'enforced'.
    status = 'pending-stale'
    message =
      `PENDING surface "${input.surface}" is now fully covered — set its enforcement to ` +
      `'enforced' and drop the pending owner${input.pendingOwner ? ` (${input.pendingOwner})` : ''}.`
  } else {
    status = 'pending'
    message =
      `PENDING (owner: ${input.pendingOwner ?? 'unassigned'}): ${missing.length} advertised ` +
      `tool(s) not yet named in the instruction: ${missing.join(', ')}.`
  }

  return {
    surface: input.surface,
    status,
    enforcement: input.enforcement,
    advertisedCount: advertised.length,
    mentioned,
    missing,
    allowlisted,
    pendingOwner: input.pendingOwner,
    fails: FAILING_STATUSES.has(status),
    message
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
        (result.allowlisted.length ? `, ${result.allowlisted.length} allow` : '')
    )
    lines.push(`        ${result.message}`)
  }
  lines.push(report.ok ? 'Result: PASS' : `Result: FAIL (${report.violations.length} surface(s))`)
  return lines.join('\n')
}
