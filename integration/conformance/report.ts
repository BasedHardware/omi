/**
 * Structured conformance results.
 *
 * Failures name the broken guarantee in plain language. A skipped check is
 * never reported as a pass.
 */

export const GUARANTEE_IDS = [
  "client_id_idempotency",
  "revision_monotonicity",
  "keyset_stability",
  "completeness_honesty",
  "cursor_validity",
  "error_envelope",
] as const;

export type GuaranteeId = (typeof GUARANTEE_IDS)[number];

/** Plain-language names used in failure copy — never a bare boolean. */
export const GUARANTEE_LABELS: Readonly<Record<GuaranteeId, string>> = Object.freeze({
  client_id_idempotency: "client-id idempotency",
  revision_monotonicity: "revision monotonicity",
  keyset_stability: "keyset stability",
  completeness_honesty: "completeness honesty",
  cursor_validity: "cursor validity",
  error_envelope: "error envelope",
});

export type CheckOutcome = "passed" | "failed" | "skipped";

export type GuaranteeResult = {
  readonly id: GuaranteeId;
  readonly label: string;
  readonly outcome: CheckOutcome;
  /** Loud, specific explanation — what held or which mechanism broke. */
  readonly detail: string;
};

export type OracleEntryFailure = {
  readonly name: string;
  readonly expected: boolean;
  readonly actual: boolean;
  readonly detail: string;
};

export type CorpusOracleResult = {
  readonly corpus: string;
  readonly total: number;
  readonly matched: number;
  readonly mismatched: number;
  readonly failures: readonly OracleEntryFailure[];
};

export type OracleReport = {
  readonly ok: boolean;
  readonly corpora: readonly CorpusOracleResult[];
};

export type LiveReport = {
  readonly ok: boolean;
  /** True when the live half did not run because the server was unreachable. */
  readonly skipped: boolean;
  readonly skipReason: string | null;
  readonly baseUrl: string;
  readonly guarantees: readonly GuaranteeResult[];
};

export type ConformanceReport = {
  readonly ok: boolean;
  readonly oracle: OracleReport;
  readonly live: LiveReport;
};

export function guaranteeResult(
  id: GuaranteeId,
  outcome: CheckOutcome,
  detail: string,
): GuaranteeResult {
  return {
    id,
    label: GUARANTEE_LABELS[id],
    outcome,
    detail,
  };
}

export function allGuaranteesSkipped(baseUrl: string, reason: string): LiveReport {
  return {
    ok: false,
    skipped: true,
    skipReason: reason,
    baseUrl,
    guarantees: GUARANTEE_IDS.map((id) =>
      guaranteeResult(
        id,
        "skipped",
        `Live server unreachable at ${baseUrl}: ${reason}. This check did not run and is NOT a pass.`,
      ),
    ),
  };
}

export function liveReportOk(guarantees: readonly GuaranteeResult[]): boolean {
  return guarantees.every((g) => g.outcome === "passed");
}

/**
 * Human-readable summary. Failed guarantees are named in plain language.
 * Skipped checks are called out so they cannot be mistaken for passes.
 */
export function formatConformanceReport(report: ConformanceReport): string {
  const lines: string[] = [];
  lines.push("=== Contract conformance ===");
  lines.push("");
  lines.push("--- (A) Oracle self-check ---");
  for (const corpus of report.oracle.corpora) {
    const status = corpus.mismatched === 0 ? "PASS" : "FAIL";
    lines.push(
      `  [${status}] ${corpus.corpus}: ${corpus.matched}/${corpus.total} entries match oracle verdict`,
    );
    for (const failure of corpus.failures) {
      lines.push(
        `    - entry "${failure.name}": expected validator=${failure.expected}, got ${failure.actual} — ${failure.detail}`,
      );
    }
  }
  lines.push(
    report.oracle.ok
      ? "  Oracle: PASS (vendored validators match every corpus boolean)"
      : "  Oracle: FAIL (see mismatched entry names above)",
  );

  lines.push("");
  lines.push("--- (B) Live-wire conformance ---");
  lines.push(`  base URL: ${report.live.baseUrl}`);
  if (report.live.skipped) {
    lines.push(
      `  SKIPPED (not a pass): ${report.live.skipReason ?? "server not reachable"}`,
    );
  }
  for (const g of report.live.guarantees) {
    const tag =
      g.outcome === "passed" ? "PASS" : g.outcome === "failed" ? "FAIL" : "SKIP";
    lines.push(`  [${tag}] ${g.label}: ${g.detail}`);
  }

  lines.push("");
  if (report.ok) {
    lines.push("RESULT: PASS — oracle intact and every live guarantee held.");
  } else if (report.live.skipped && report.oracle.ok) {
    lines.push(
      "RESULT: INCOMPLETE — oracle passed, but live guarantees were SKIPPED (server down). Skips are not passes.",
    );
  } else {
    const broken = report.live.guarantees
      .filter((g) => g.outcome === "failed")
      .map((g) => g.label);
    const oracleBroken = report.oracle.ok ? [] : ["oracle self-check"];
    const names = [...oracleBroken, ...broken];
    lines.push(
      names.length > 0
        ? `RESULT: FAIL — broken guarantee(s): ${names.join(", ")}`
        : "RESULT: FAIL — see details above",
    );
  }
  return lines.join("\n");
}
