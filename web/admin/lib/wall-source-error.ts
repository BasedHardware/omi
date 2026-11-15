/** Only controlled descriptions may reach cards/logs; upstream bodies can contain secrets. */
export class WallSourceError extends Error {
  constructor(message: string, readonly retryable = false) {
    super(message);
    this.name = "WallSourceError";
  }
}
/** A BigQuery read that failed because the admin's reader identity has no grant
 * on, or cannot find, one of the tables the query reads. Before 2026-10-28 every
 * such failure surfaced as "table not created" or "key lacks scope", which hid
 * five unreadable `omi_finops` tables behind the blank margin tiles. Only names
 * from `tables` (the caller's own constants) can reach the message; the upstream
 * text is matched, never forwarded. Anything else gets `fallback`. */
export function bigQueryFailure(
  error: unknown,
  tables: readonly string[],
  fallback: string,
  retryable = false
): WallSourceError {
  const e = error as {
    code?: number;
    message?: string;
    errors?: { reason?: string }[];
  } | null;
  const reason = e?.errors?.[0]?.reason;
  const text = typeof e?.message === "string" ? e.message : "";
  // Name a table only when the upstream error itself names it: a project-level
  // denial (e.g. bigquery.jobs.create) is not a table grant problem.
  const table = tables.find((t) =>
    new RegExp(`Table [\\w-]+:${t.replace(".", "\\.")}\\b`).test(text)
  );
  const denied =
    e?.code === 403 || reason === "accessDenied" || /Access Denied/.test(text);
  if (denied && table)
    return new WallSourceError(
      `${table} not readable by the admin BigQuery identity (missing dataViewer grant)`
    );
  if (denied)
    return new WallSourceError(
      "FinOps BigQuery permission denied for the admin identity (not table-specific)",
      retryable
    );
  const missing =
    e?.code === 404 || reason === "notFound" || /^Not found/.test(text);
  if (missing && table)
    return new WallSourceError(`${table} not found (table not created yet)`);
  return new WallSourceError(fallback, retryable);
}

export function wallFailure(source: string, error: unknown): string {
  if (error instanceof WallSourceError) return error.message;
  if (
    error instanceof Error &&
    ["TimeoutError", "AbortError"].includes(error.name)
  )
    return `${source} request timed out`;
  return `${source} request failed; check source connectivity/configuration`;
}
