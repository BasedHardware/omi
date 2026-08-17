/**
 * Fixture time anchor for the integration harness.
 *
 * WHY THIS FILE EXISTS AT ALL
 * ---------------------------
 * A fixed UTC seed is *not* sufficient for a full-stack harness. The backend
 * seeds instants; the surfaces group them into Today / Tomorrow / Later using
 * the *host's local* zone. So an assertion like "this item renders under
 * Today" silently depends on the timezone of whatever machine runs the suite,
 * and drifts between a laptop in California and CI in UTC. That is a real
 * class of overnight flake, not a hypothetical.
 *
 * THE RULE
 * --------
 * 1. The harness forces `TZ=UTC` into every child process it spawns (backend,
 *    vite, shells, simulator host env). Local time therefore *equals* UTC for
 *    every participant, so "server instant" and "rendered day bucket" cannot
 *    disagree.
 * 2. The anchor is 2026-01-15T12:00:00Z — deliberately **midday** UTC. If TZ
 *    enforcement ever fails on one participant, a midday anchor still lands on
 *    the same calendar date for every zone in UTC-11..UTC+11, so the failure
 *    shows up as a *drifted* assertion somewhere obvious rather than as an
 *    intermittent off-by-one-day that only reproduces near midnight.
 * 3. Nothing in the harness may call `Date.now()` for fixture data. Import
 *    `FIXTURE_ANCHOR_EPOCH_SECONDS` instead.
 *
 * Both facts are asserted at runtime by `assertFixtureTimezone()`, so a run
 * that forgot the TZ export fails loudly instead of producing plausible
 * wrong answers.
 */

/** 2026-01-15T12:00:00Z. Midday UTC — see rule 2 above. */
export const FIXTURE_ANCHOR_ISO = "2026-01-15T12:00:00.000Z";
export const FIXTURE_ANCHOR_EPOCH_MS = Date.parse(FIXTURE_ANCHOR_ISO);
export const FIXTURE_ANCHOR_EPOCH_SECONDS = Math.floor(FIXTURE_ANCHOR_EPOCH_MS / 1000);

/** The one timezone every harness participant must agree on. */
export const FIXTURE_TIMEZONE = "UTC";

export interface FixtureTimezoneReport {
  readonly ok: boolean;
  readonly envTz: string | undefined;
  readonly resolvedTz: string;
  readonly anchorLocalDate: string;
  readonly reason?: string;
}

/**
 * Verifies this process actually agrees with the documented anchor.
 *
 * Checks the *resolved* zone rather than trusting `process.env.TZ`, because a
 * child can inherit a TZ string the runtime never applied.
 */
export function checkFixtureTimezone(): FixtureTimezoneReport {
  const envTz = process.env.TZ;
  const resolvedTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const offsetMinutes = new Date(FIXTURE_ANCHOR_EPOCH_MS).getTimezoneOffset();
  const anchorLocalDate = formatLocalDate(new Date(FIXTURE_ANCHOR_EPOCH_MS));

  if (offsetMinutes !== 0) {
    return {
      ok: false,
      envTz,
      resolvedTz,
      anchorLocalDate,
      reason:
        `fixture timezone anchor violated: this process resolves local time to `
        + `"${resolvedTz}" (UTC offset ${-offsetMinutes} minutes), not ${FIXTURE_TIMEZONE}. `
        + `Day-bucket assertions would drift. Export TZ=${FIXTURE_TIMEZONE} for every child.`,
    };
  }

  return { ok: true, envTz, resolvedTz, anchorLocalDate };
}

export function assertFixtureTimezone(): FixtureTimezoneReport {
  const report = checkFixtureTimezone();
  if (!report.ok) {
    throw new Error(report.reason ?? "fixture timezone anchor violated");
  }
  return report;
}

function formatLocalDate(date: Date): string {
  const year = String(date.getFullYear()).padStart(4, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
